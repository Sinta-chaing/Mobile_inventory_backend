"""
Image Search Service using CLIP and Qdrant Vector Database
"""
import os
import io
import numpy as np
from PIL import Image
import torch
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
import requests
from typing import List, Dict, Any, Tuple, Optional
import time
import glob
import atexit
import sys

# Configuration
QDRANT_PATH = os.path.join(settings.BASE_DIR, "qdrant_storage")
COLLECTION_NAME = "product_images"
VECTOR_SIZE = 768  # CLIP embedding size

# Global instances (lazy-initialized)
_client_instance = None
_clip_model = None
_clip_preprocess = None
_device = None
_yolo_model = None
_is_auto_indexing = False  # Guard against recursive auto-indexing
_skip_auto_index = False   # Used by management command to skip auto-indexing

def _cleanup_client():
    """Properly close Qdrant client on shutdown"""
    global _client_instance
    try:
        if _client_instance is not None and hasattr(_client_instance, 'close'):
            _client_instance.close()
    except:
        pass
    _client_instance = None

# Register cleanup on exit
atexit.register(_cleanup_client)

def _get_device():
    """Get the device for PyTorch (lazy-initialized)"""
    global _device
    if _device is None:
        _device = "cuda" if torch.cuda.is_available() else "cpu"
    return _device

def _get_clip_model():
    """Get CLIP model (lazy-initialized)"""
    global _clip_model, _clip_preprocess
    if _clip_model is None:
        import clip
        device = _get_device()
        _clip_model, _clip_preprocess = clip.load("ViT-L/14@336px", device=device)
    return _clip_model, _clip_preprocess

def _get_yolo_model():
    """Get YOLO model (lazy-initialized and cached)"""
    global _yolo_model
    if _yolo_model is None:
        from ultralytics import YOLO
        yolo_path = getattr(settings, 'IMAGE_SEARCH_YOLO_MODEL', 'yolo11n.pt')
        _yolo_model = YOLO(yolo_path)
    return _yolo_model

def load_pil_image(image_source) -> Image.Image:
    """Load PIL Image from source, resolve local media path, apply EXIF transpose, convert to RGB"""
    from PIL import ImageOps
    
    if isinstance(image_source, str):
        # Convert media URL to local path if possible
        if '/media/' in image_source:
            media_part = image_source.split('/media/')[-1]
            local_path = os.path.join(settings.MEDIA_ROOT, media_part)
            if os.path.exists(local_path):
                image_source = local_path
                
        if image_source.startswith(('http://', 'https://')):
            response = requests.get(image_source, timeout=10)
            image = Image.open(io.BytesIO(response.content))
        elif image_source.startswith('/media/'):
            # Convert to absolute path
            media_path = os.path.join(settings.BASE_DIR, '..', 'backend', image_source.lstrip('/'))
            if not os.path.exists(media_path):
                media_path = os.path.join(settings.BASE_DIR, image_source.lstrip('/'))
            image = Image.open(media_path)
        else:
            image = Image.open(image_source)
    elif isinstance(image_source, UploadedFile):
        image = Image.open(image_source)
    elif isinstance(image_source, Image.Image):
        image = image_source
    else:
        raise ValueError("Invalid image source type")
        
    # Apply EXIF orientation correction
    image = ImageOps.exif_transpose(image)
    
    if image.mode != 'RGB':
        image = image.convert('RGB')
        
    return image

def run_yolo_detection(image: Image.Image) -> List[Dict[str, Any]]:
    """
    Run YOLO on PIL image and return all detections with bounding boxes.
    Detections contain: 'bbox' [x1, y1, x2, y2], 'confidence', 'class'.
    """
    try:
        # Convert PIL to BGR numpy array
        open_cv_image = np.array(image)
        # Convert RGB to BGR
        open_cv_image = open_cv_image[:, :, ::-1].copy()
        
        yolo_model = _get_yolo_model()
        results = yolo_model(open_cv_image, conf=0.25, verbose=False)
        
        detections = []
        for result in results:
            boxes = result.boxes
            for box in boxes:
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                confidence = float(box.conf[0].cpu().numpy())
                class_id = int(box.cls[0].cpu().numpy())
                class_name = result.names[class_id]
                detections.append({
                    'bbox': [int(x1), int(y1), int(x2), int(y2)],
                    'confidence': confidence,
                    'class': class_name
                })
                
        return detections
    except Exception as e:
        print(f"YOLO detection error: {e}")
    return []

def crop_pil_image(image: Image.Image, bbox: List[int], padding: int = 10) -> Image.Image:
    """Crop PIL Image based on bounding box with padding"""
    try:
        x1, y1, x2, y2 = bbox
        w, h = image.size
        
        # Add padding while keeping within image bounds
        x1 = max(0, x1 - padding)
        y1 = max(0, y1 - padding)
        x2 = min(w, x2 + padding)
        y2 = min(h, y2 + padding)
        
        return image.crop((x1, y1, x2, y2))
    except Exception as e:
        print(f"PIL crop error: {e}")
    return image

def _cleanup_lock_files():
    """Remove lock files that might be blocking Qdrant"""
    try:
        # Remove lock files
        lock_patterns = [
            os.path.join(QDRANT_PATH, "*.lock"),
            os.path.join(QDRANT_PATH, "**/*.lock"),
        ]
        for pattern in lock_patterns:
            for lock_file in glob.glob(pattern, recursive=True):
                try:
                    os.remove(lock_file)
                except:
                    pass
        time.sleep(0.5)  # Brief delay to ensure locks are released
    except:
        pass

def initialize_qdrant(auto_index=True):
    """Initialize Qdrant client and create collection if needed.
    
    Args:
        auto_index: If True and collection is empty, auto-index products from database
    """
    global _client_instance, _is_auto_indexing, _skip_auto_index
    
    try:
        os.makedirs(QDRANT_PATH, exist_ok=True)
        
        # Clean up any lock files
        _cleanup_lock_files()
        
        # Create or reuse client
        if _client_instance is None:
            _client_instance = QdrantClient(path=QDRANT_PATH)
        
        try:
            # Check if collection exists and how many points it has
            collection_info = _client_instance.get_collection(COLLECTION_NAME)
            
            # Check vector size of existing collection
            existing_size = 0
            if hasattr(collection_info, 'config') and hasattr(collection_info.config, 'params') and hasattr(collection_info.config.params, 'vectors'):
                vectors_config = collection_info.config.params.vectors
                if hasattr(vectors_config, 'size'):
                    existing_size = vectors_config.size
                elif isinstance(vectors_config, dict) and 'size' in vectors_config:
                    existing_size = vectors_config['size']
            
            if existing_size != VECTOR_SIZE:
                print(f"INFO: Vector size mismatch (existing: {existing_size}, target: {VECTOR_SIZE}). Recreating collection...")
                from qdrant_client.models import VectorParams, Distance
                _client_instance.recreate_collection(
                    collection_name=COLLECTION_NAME,
                    vectors_config=VectorParams(
                        size=VECTOR_SIZE,
                        distance=Distance.COSINE
                    )
                )
                points_count = 0
            else:
                points_count = collection_info.points_count if hasattr(collection_info, 'points_count') else 0
            
            # If collection is empty, auto-index (unless disabled)
            if auto_index and not _skip_auto_index and points_count == 0 and not _is_auto_indexing:
                print(f"INFO: Collection '{COLLECTION_NAME}' is empty. Auto-indexing products from database...")
                _is_auto_indexing = True
                try:
                    _auto_index_products()
                finally:
                    _is_auto_indexing = False
                    
        except Exception as e:
            # Collection doesn't exist, create it
            if not _skip_auto_index:
                print(f"Creating new collection: {str(e)}")
            from qdrant_client.models import VectorParams, Distance
            _client_instance.recreate_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(
                    size=VECTOR_SIZE,
                    distance=Distance.COSINE
                )
            )
            # Auto-index after creation if enabled and not already doing so
            if auto_index and not _skip_auto_index and not _is_auto_indexing:
                print(f"New collection created. Auto-indexing products from database...")
                _is_auto_indexing = True
                try:
                    _auto_index_products()
                finally:
                    _is_auto_indexing = False
        
        return _client_instance
    except Exception as e:
        raise Exception(f"Failed to initialize Qdrant: {str(e)}")

def _auto_index_products():
    """Automatically index all products with images from the database"""
    try:
        from api.models import Product
        
        products = Product.objects.filter(image__isnull=False).exclude(image="")
        count = 0
        for product in products:
            try:
                if index_product_image(
                    product.productId,
                    product.image,
                    product.productName,
                    product.skuCode
                ):
                    count += 1
            except Exception as e:
                print(f"Failed to index {product.productName}: {str(e)}")
        
        print(f"Auto-indexed {count} products from database")
    except Exception as e:
        print(f"Error during auto-indexing: {str(e)}")

def get_image_embedding(image_source):
    """
    Generate embedding for an image
    
    Args:
        image_source: PIL Image, file path, or URL
    
    Returns:
        numpy array of embedding
    """
    try:
        image = load_pil_image(image_source)
        
        # Get lazy-loaded CLIP model
        model, preprocess = _get_clip_model()
        device = _get_device()
        
        # Preprocess and get embedding
        image_tensor = preprocess(image).unsqueeze(0).to(device)
        
        with torch.no_grad():
            embedding = model.encode_image(image_tensor)
        
        # Normalize embedding
        embedding = embedding / embedding.norm(dim=-1, keepdim=True)
        return embedding[0].cpu().numpy().astype(np.float32)
    
    except Exception as e:
        print(f"Error generating embedding: {str(e)}")
        raise

def index_product_image(product_id: int, image_url: str, product_name: str = "", sku_code: str = ""):
    """
    Add or update a product image in the vector database
    
    Args:
        product_id: Unique product ID
        image_url: URL or path to image
        product_name: Product name
        sku_code: Product SKU
    """
    try:
        client = initialize_qdrant()
        
        # Get embedding
        embedding = get_image_embedding(image_url)
        
        # Create point with metadata
        point = PointStruct(
            id=product_id,
            vector=embedding.tolist(),
            payload={
                "product_id": product_id,
                "image_url": image_url,
                "product_name": product_name,
                "sku_code": sku_code,
            }
        )
        
        # Upsert point (insert or update)
        client.upsert(
            collection_name=COLLECTION_NAME,
            points=[point]
        )
        
        return True
    except Exception as e:
        print(f"Error indexing product image: {str(e)}")
        return False

def _search_qdrant(client, query_vector, top_k, score_threshold):
    """
    Search in Qdrant collection.
    
    Args:
        client: QdrantClient instance
        query_vector: Query embedding as list
        top_k: Number of results
        score_threshold: Minimum similarity score
    
    Returns:
        List of ScoredPoint objects with payload
    """
    try:
        # query_points is the unified API method in qdrant-client >= 1.16.0
        response = client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            limit=top_k,
            score_threshold=score_threshold,
            with_payload=True,
        )
        return response.points if (response and hasattr(response, 'points')) else []
        
    except Exception as e:
        print(f"Error searching Qdrant: {str(e)}")
        return []

def _format_search_results(search_points):
    """Helper to convert Qdrant search points to enriched result dicts"""
    from api.models import Product
    results = []
    
    for point in search_points:
        if point.payload is None:
            payload = {}
        elif isinstance(point.payload, dict):
            payload = point.payload
        elif hasattr(point.payload, '__dict__'):
            payload = point.payload.__dict__
        else:
            payload = {}
        
        score = point.score if hasattr(point, 'score') else 0
        
        result_data = {
            "product_id": payload.get("product_id") if isinstance(payload, dict) else None,
            "product_name": payload.get("product_name") if isinstance(payload, dict) else None,
            "sku_code": payload.get("sku_code") if isinstance(payload, dict) else None,
            "image_url": payload.get("image_url") if isinstance(payload, dict) else None,
            "similarity_score": score,
        }
        
        try:
            product_id = payload.get("product_id") if isinstance(payload, dict) else None
            if product_id:
                product = Product.objects.get(productId=product_id)
                result_data["sale_price"] = float(product.salePrice)
                result_data["cost_price"] = float(product.costPrice)
            else:
                result_data["sale_price"] = 0.0
                result_data["cost_price"] = 0.0
        except Product.DoesNotExist:
            result_data["sale_price"] = 0.0
            result_data["cost_price"] = 0.0
        except Exception as e:
            product_id = payload.get("product_id") if isinstance(payload, dict) else None
            if product_id:
                print(f"Warning: Could not fetch product data for ID {product_id}: {e}")
            result_data["sale_price"] = 0.0
            result_data["cost_price"] = 0.0
        
        results.append(result_data)
        
    return results

def search_similar_images(
    image_source,
    top_k: int = 10,
    score_threshold: float = 0.5,
    crop_rect: Optional[Dict[str, int]] = None
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Search for similar products based on image.
    Supports manual crop rect and automatic YOLO detection.
    Falls back to full image search if the best crop match score is < 0.68.
    
    Returns:
        Tuple of (results, detections)
    """
    try:
        client = initialize_qdrant()
        
        # Debug: Check collection state
        try:
            collection_info = client.get_collection(COLLECTION_NAME)
            print(f"DEBUG: Collection '{COLLECTION_NAME}' has {collection_info.points_count} points")
        except Exception as e:
            print(f"DEBUG: Error checking collection: {e}")
            
        # Load base image (with orientation correction)
        base_image = load_pil_image(image_source)
        
        cropped_image = None
        yolo_detections = []
        
        # 1. Check if crop coords are provided by client (manual crop)
        if crop_rect is not None:
            try:
                x1 = crop_rect.get('x1', 0)
                y1 = crop_rect.get('y1', 0)
                x2 = crop_rect.get('x2', base_image.width)
                y2 = crop_rect.get('y2', base_image.height)
                cropped_image = base_image.crop((x1, y1, x2, y2))
                print(f"DEBUG: Using manual crop rect: {x1}, {y1}, {x2}, {y2}")
            except Exception as e:
                print(f"Error manual cropping: {e}")
        else:
            # 2. Run YOLO auto-detection
            detections = run_yolo_detection(base_image)
            if detections:
                # Format detections for response compatibility
                for d in detections:
                    yolo_detections.append({
                        'class_name': d['class'],
                        'class': d['class'],
                        'confidence': d['confidence'],
                        'bbox': d['bbox']
                    })
                # Pick best detection for crop
                best_det = max(detections, key=lambda x: x['confidence'])
                cropped_image = crop_pil_image(base_image, best_det['bbox'])
                print(f"DEBUG: YOLO auto-cropped using best detection '{best_det['class']}' with confidence {best_det['confidence']:.4f}")
            else:
                print("DEBUG: YOLO detected no objects")
                
        # 3. Perform primary search using cropped image (or full image if crop wasn't possible)
        query_image = cropped_image if cropped_image is not None else base_image
        query_embedding = get_image_embedding(query_image)
        search_points = _search_qdrant(client, query_embedding.tolist(), top_k, score_threshold)
        results = _format_search_results(search_points)
        
        # 4. Fallback Mechanism:
        # If we used a cropped image and the highest similarity score is < 0.68,
        # perform a secondary search using the full image and select the stronger set of results.
        # Fallback is only triggered for automatic crops (crop_rect is None), not user manual crops.
        max_score = max([r['similarity_score'] for r in results]) if results else 0.0
        
        if crop_rect is None and cropped_image is not None and max_score < 0.68:
            print(f"DEBUG: Crop match is weak (max score: {max_score:.4f} < 0.68). Performing full-image fallback search...")
            fallback_embedding = get_image_embedding(base_image)
            fallback_points = _search_qdrant(client, fallback_embedding.tolist(), top_k, score_threshold)
            fallback_results = _format_search_results(fallback_points)
            
            fallback_max_score = max([r['similarity_score'] for r in fallback_results]) if fallback_results else 0.0
            
            if fallback_max_score > max_score:
                print(f"DEBUG: Full-image fallback results are stronger (max score: {fallback_max_score:.4f} > {max_score:.4f}). Choosing fallback.")
                results = fallback_results
            else:
                print(f"DEBUG: Cropped results remain stronger ({max_score:.4f} >= {fallback_max_score:.4f}). Keeping crop.")
                
        print(f"DEBUG: Returning {len(results)} search results and {len(yolo_detections)} detections")
        return results, yolo_detections
    except Exception as e:
        print(f"Error searching images: {str(e)}")
        return [], []
    
    except Exception as e:
        print(f"Error searching images: {str(e)}")
        return []

def get_collection_info():
    """Get information about the vector collection"""
    try:
        client = initialize_qdrant()
        info = client.get_collection(COLLECTION_NAME)
        return {
            "collection_name": COLLECTION_NAME,
            "vector_size": VECTOR_SIZE,
            "points_count": info.points_count,
        }
    except Exception as e:
        print(f"Error getting collection info: {str(e)}")
        return None
