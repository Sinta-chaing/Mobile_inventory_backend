"""
Debug script for Image Search Service
Tests the entire pipeline: Qdrant connection, indexing, and search
"""
import os
import sys
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

import django
django.setup()

from api.image_search_service import (
    initialize_qdrant, 
    get_collection_info,
    get_image_embedding,
    search_similar_images
)
from django.conf import settings
from PIL import Image
import numpy as np

# Get IMAGES_DIR
IMAGES_DIR = os.path.join(settings.BASE_DIR, '..', 'Images')

print("=" * 60)
print("IMAGE SEARCH SERVICE DIAGNOSTIC")
print("=" * 60)

# 1. Check Qdrant Connection
print("\n[1] Checking Qdrant Connection...")
try:
    client = initialize_qdrant()
    print("✓ Qdrant client initialized successfully")
except Exception as e:
    print(f"✗ Failed to initialize Qdrant: {e}")
    sys.exit(1)

# 2. Check Collection Info
print("\n[2] Checking Collection Info...")
try:
    info = get_collection_info()
    if info:
        print(f"✓ Collection: {info['collection_name']}")
        print(f"✓ Vector Size: {info['vector_size']}")
        print(f"✓ Indexed Images: {info['points_count']}")
        
        if info['points_count'] == 0:
            print("⚠ WARNING: No images indexed! Run initialization first.")
            print("  Command: python manage.py initialize_image_search --reset --local-only")
        else:
            print(f"✓ Successfully indexed {info['points_count']} images")
    else:
        print("✗ Collection info not available")
except Exception as e:
    print(f"✗ Error getting collection info: {e}")

# 3. Check Images Directory
print("\n[3] Checking Images Directory...")
if os.path.exists(IMAGES_DIR):
    image_files = [f for f in os.listdir(IMAGES_DIR) 
                   if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'))]
    print(f"✓ Images directory found: {IMAGES_DIR}")
    print(f"✓ Found {len(image_files)} image files")
    if image_files:
        print(f"  Sample images: {image_files[:3]}")
else:
    print(f"✗ Images directory not found: {IMAGES_DIR}")

# 4. Test CLIP Model
print("\n[4] Testing CLIP Model...")
try:
    import clip
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"✓ Using device: {device}")
    print(f"✓ PyTorch available: {torch.__version__}")
    print(f"✓ CLIP available: {clip.__version__ if hasattr(clip, '__version__') else 'imported'}")
except Exception as e:
    print(f"✗ Error with CLIP/PyTorch: {e}")

# 5. Test Embedding Generation
print("\n[5] Testing Embedding Generation...")
try:
    # Get first image file
    image_files = [f for f in os.listdir(IMAGES_DIR) 
                   if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'))]
    if image_files:
        test_image_path = os.path.join(IMAGES_DIR, image_files[0])
        embedding = get_image_embedding(test_image_path)
        print(f"✓ Generated embedding for: {image_files[0]}")
        print(f"✓ Embedding shape: {embedding.shape}")
        print(f"✓ Embedding dtype: {embedding.dtype}")
        print(f"✓ Embedding norm: {np.linalg.norm(embedding):.4f}")
    else:
        print("⚠ No images available for testing")
except Exception as e:
    print(f"✗ Error generating embedding: {e}")

# 6. Test Query
print("\n[6] Testing Query/Search...")
try:
    info = get_collection_info()
    if info and info['points_count'] > 0:
        # Get first image for testing
        image_files = [f for f in os.listdir(IMAGES_DIR) 
                       if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'))]
        if image_files:
            test_image_path = os.path.join(IMAGES_DIR, image_files[0])
            
            # Try different thresholds
            for threshold in [0.0, 0.1, 0.3]:
                results, detections = search_similar_images(test_image_path, top_k=5, score_threshold=threshold)
                print(f"✓ Query with threshold={threshold}: Found {len(results)} results")
                if results:
                    for i, result in enumerate(results[:2], 1):
                        print(f"    {i}. {result['product_name']} (score: {result['similarity_score']:.4f})")
        else:
            print("⚠ No images available for testing")
    else:
        print("⚠ Collection is empty, cannot test search")
except Exception as e:
    print(f"✗ Error during search: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("DIAGNOSTIC COMPLETE")
print("=" * 60)
