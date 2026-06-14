"""
Image Search Views using CLIP and Qdrant
"""
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
import io
from PIL import Image
from django.views.decorators.csrf import csrf_exempt
import logging

logger = logging.getLogger(__name__)

try:
    from .image_search_service import search_similar_images, index_product_image
except ImportError:
    logger.warning("Image search service not available")

@api_view(['POST'])
@parser_classes((MultiPartParser, FormParser))
@permission_classes([IsAuthenticated])
def search_products_by_image(request):
    """
    Search for similar products by uploading an image.
    
    POST /api/search-products/
    
    Expected parameters:
    - file: Image file (multipart/form-data)
    - top_k: Number of results (optional, default: 10)
    - score_threshold: Minimum similarity score (optional, default: 0.5)
    
    Returns:
    - results: List of matching products with similarity scores
    """
    try:
        logger.info(f"Search request from user: {request.user}")
        
        # Get uploaded file
        image_file = request.FILES.get('file')
        if not image_file:
            logger.error("No image file provided in request")
            return Response(
                {'error': 'No image file provided'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        logger.info(f"Received image file: {image_file.name}, size: {image_file.size} bytes")
        
        # Validate image format by trying to open it
        image_file.seek(0)
        try:
            img = Image.open(image_file)
            img.load()  # Load to verify it's a valid image
            logger.info(f"Image validated: {img.format} {img.size}")
        except Exception as e:
            logger.error(f"Invalid image file: {str(e)}")
            return Response(
                {'error': f'Invalid image file: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Reset file pointer back to start for search
        image_file.seek(0)
        
        # Get search parameters
        top_k = int(request.data.get('top_k', 10))
        score_threshold = float(request.data.get('score_threshold', 0.3))  # Lowered from 0.5
        
        # Parse crop coordinates if provided
        crop_json = request.data.get('crop')
        crop_rect = None
        if crop_json:
            try:
                import json
                crop_rect = json.loads(crop_json)
                logger.info(f"Received crop rect: {crop_rect}")
            except Exception as e:
                logger.error(f"Failed to parse crop JSON: {e}")
                
        # Validate parameters
        top_k = max(1, min(top_k, 50))  # Limit to 1-50
        score_threshold = max(0.0, min(score_threshold, 1.0))
        
        logger.info(f"Search parameters: top_k={top_k}, score_threshold={score_threshold}")
        
        # Search for similar images
        results, detections = search_similar_images(
            image_file,
            top_k=top_k,
            score_threshold=score_threshold,
            crop_rect=crop_rect
        )
        
        logger.info(f"Search returned {len(results)} results, {len(detections)} detections")
        
        return Response({
            'success': True,
            'results': results,
            'count': len(results),
            'detections': detections,
            'parameters': {
                'top_k': top_k,
                'score_threshold': score_threshold
            }
        })
    
    except Exception as e:
        logger.error(f"Error searching by image: {str(e)}")
        return Response(
            {'error': f'Search failed: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def search_products_by_url(request):
    """
    Search for similar products by image URL.
    
    GET /api/search-products-url/
    
    Expected query parameters:
    - image_url: URL to image (required)
    - top_k: Number of results (optional, default: 10)
    - score_threshold: Minimum similarity score (optional, default: 0.5)
    
    Returns:
    - results: List of matching products with similarity scores
    """
    try:
        # Get image URL
        image_url = request.query_params.get('image_url')
        if not image_url:
            return Response(
                {'error': 'image_url query parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get search parameters
        top_k = int(request.query_params.get('top_k', 10))
        score_threshold = float(request.query_params.get('score_threshold', 0.5))
        
        # Parse crop coordinates if provided
        crop_json = request.query_params.get('crop')
        crop_rect = None
        if crop_json:
            try:
                import json
                crop_rect = json.loads(crop_json)
            except Exception as e:
                pass
                
        # Validate parameters
        top_k = max(1, min(top_k, 50))
        score_threshold = max(0.0, min(score_threshold, 1.0))
        
        # Search for similar images
        results, detections = search_similar_images(
            image_url,
            top_k=top_k,
            score_threshold=score_threshold,
            crop_rect=crop_rect
        )
        
        return Response({
            'success': True,
            'results': results,
            'count': len(results),
            'detections': detections,
            'parameters': {
                'image_url': image_url,
                'top_k': top_k,
                'score_threshold': score_threshold
            }
        })
    
    except Exception as e:
        logger.error(f"Error searching by URL: {str(e)}")
        return Response(
            {'error': f'Search failed: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def index_product_images(request):
    """
    Index/reindex product images for vector search.
    
    POST /api/index-product-images/
    
    Expected JSON body:
    - product_id: ID of product (required)
    - image_url: URL or path to image (required)
    - product_name: Product name (optional)
    - sku_code: Product SKU (optional)
    
    Or for batch indexing:
    - mode: 'batch' 
    - products: List of product objects
    
    Returns:
    - success: Boolean indicating if indexing was successful
    - message: Status message
    """
    try:
        # Check if user has permission (admin/manager)
        from .permissions import IsAdminOrManager
        if not IsAdminOrManager().has_permission(request, None):
            return Response(
                {'error': 'Only admins/managers can index images'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        mode = request.data.get('mode', 'single')
        
        if mode == 'batch':
            # Batch indexing
            products = request.data.get('products', [])
            indexed_count = 0
            errors = []
            
            for product_data in products:
                try:
                    success = index_product_image(
                        product_id=product_data.get('product_id'),
                        image_url=product_data.get('image_url'),
                        product_name=product_data.get('product_name', ''),
                        sku_code=product_data.get('sku_code', '')
                    )
                    if success:
                        indexed_count += 1
                    else:
                        errors.append(f"Failed to index product {product_data.get('product_id')}")
                except Exception as e:
                    errors.append(f"Error indexing product {product_data.get('product_id')}: {str(e)}")
            
            return Response({
                'success': len(errors) == 0,
                'message': f'Indexed {indexed_count} products',
                'indexed_count': indexed_count,
                'errors': errors if errors else None
            })
        
        else:
            # Single product indexing
            product_id = request.data.get('product_id')
            image_url = request.data.get('image_url')
            
            if not product_id or not image_url:
                return Response(
                    {'error': 'product_id and image_url are required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            success = index_product_image(
                product_id=product_id,
                image_url=image_url,
                product_name=request.data.get('product_name', ''),
                sku_code=request.data.get('sku_code', '')
            )
            
            return Response({
                'success': success,
                'message': 'Product image indexed successfully' if success else 'Failed to index product image',
                'product_id': product_id
            })
    
    except Exception as e:
        logger.error(f"Error indexing product images: {str(e)}")
        return Response(
            {'error': f'Indexing failed: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
