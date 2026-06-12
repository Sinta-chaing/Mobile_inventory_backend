"""
Test script for Image Search API endpoints
Tests health check, image search, product indexing, and batch operations
"""

import requests
import json
import sys
from pathlib import Path
from typing import Optional, Dict
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


class ImageSearchAPITester:
    """Test Image Search API endpoints"""
    
    def __init__(self, base_url: str = "http://127.0.0.1:8000/", token: Optional[str] = None):
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.session = requests.Session()
        if token:
            self.session.headers.update({'Authorization': f'Token {token}'})
        self.results = {
            'passed': 0,
            'failed': 0,
            'errors': []
        }
    
    def print_test(self, name: str, passed: bool, message: str = ""):
        """Print test result"""
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"\n{status}: {name}")
        if message:
            print(f"  {message}")
        
        if passed:
            self.results['passed'] += 1
        else:
            self.results['failed'] += 1
            self.results['errors'].append({'test': name, 'message': message})
    
    def test_health_check(self) -> bool:
        """Test health check endpoint"""
        try:
            url = f"{self.base_url}/api/image-search/health/"
            response = self.session.get(url)
            passed = response.status_code == 200
            
            data = response.json()
            message = f"Status: {data.get('status')}, Collection: {data.get('collection', {}).get('name', 'N/A')}"
            self.print_test("Health Check", passed, message)
            return passed
        except Exception as e:
            self.print_test("Health Check", False, str(e))
            return False
    
    def test_search_by_file(self, image_path: str) -> bool:
        """Test image search by file upload"""
        try:
            if not Path(image_path).exists():
                self.print_test("Search by File", False, f"Image not found: {image_path}")
                return False
            
            with open(image_path, 'rb') as f:
                files = {'file': f}
                data = {'top_k': 5, 'score_threshold': 0.5}
                
                url = f"{self.base_url}/api/search-products/"
                response = self.session.post(url, files=files, data=data)
            
            passed = response.status_code == 200
            resp_data = response.json()
            
            message = f"Status Code: {response.status_code}, Results: {resp_data.get('count', 0)}"
            self.print_test("Search by File", passed, message)
            return passed
        except Exception as e:
            self.print_test("Search by File", False, str(e))
            return False
    
    def test_search_by_url(self, image_url: str) -> bool:
        """Test image search by URL"""
        try:
            params = {
                'image_url': image_url,
                'top_k': 5,
                'score_threshold': 0.5
            }
            
            url = f"{self.base_url}/api/search-products-url/"
            response = self.session.get(url, params=params)
            
            passed = response.status_code == 200
            resp_data = response.json()
            
            message = f"Status Code: {response.status_code}, Results: {resp_data.get('count', 0)}"
            self.print_test("Search by URL", passed, message)
            return passed
        except Exception as e:
            self.print_test("Search by URL", False, str(e))
            return False
    
    def test_index_product(self, product_id: int, image_url: str) -> bool:
        """Test product image indexing"""
        try:
            url = f"{self.base_url}/api/products/{product_id}/index-image/"
            data = {'image_url': image_url}
            
            response = self.session.post(url, json=data)
            passed = response.status_code in [200, 201]
            resp_data = response.json()
            
            message = f"Status Code: {response.status_code}, Success: {resp_data.get('success', False)}"
            self.print_test(f"Index Product {product_id}", passed, message)
            return passed
        except Exception as e:
            self.print_test(f"Index Product {product_id}", False, str(e))
            return False
    
    def test_batch_index(self) -> bool:
        """Test batch product indexing"""
        try:
            url = f"{self.base_url}/api/batch-index-products/"
            response = self.session.post(url)
            
            passed = response.status_code == 200
            resp_data = response.json()
            
            message = f"Status Code: {response.status_code}, Total: {resp_data.get('total', 0)}, Successful: {resp_data.get('successful', 0)}"
            self.print_test("Batch Index Products", passed, message)
            return passed
        except Exception as e:
            self.print_test("Batch Index Products", False, str(e))
            return False
    
    def test_authentication(self) -> bool:
        """Test API authentication requirement"""
        try:
            # Try without token
            session_no_token = requests.Session()
            url = f"{self.base_url}/api/image-search/health/"
            response = session_no_token.get(url)
            
            passed = response.status_code == 401  # Should be unauthorized
            message = f"Status Code: {response.status_code} (expected 401 without token)"
            self.print_test("Authentication Check", passed, message)
            return passed
        except Exception as e:
            self.print_test("Authentication Check", False, str(e))
            return False
    
    def print_summary(self):
        """Print test summary"""
        total = self.results['passed'] + self.results['failed']
        print("\n" + "=" * 60)
        print(f"Test Summary: {self.results['passed']}/{total} passed")
        print("=" * 60)
        
        if self.results['errors']:
            print("\nFailed Tests:")
            for error in self.results['errors']:
                print(f"  - {error['test']}: {error['message']}")
        
        return self.results['failed'] == 0


def main():
    """Run all tests"""
    print("=" * 60)
    print("Image Search API Test Suite")
    print("=" * 60)
    
    # Configuration
    base_url = "http://127.0.0.1:8000/"
    token = None  # Set this to your actual token for authenticated tests
    
    print(f"\nBase URL: {base_url}")
    print(f"Authentication: {'Enabled' if token else 'Disabled (set token to enable)'}")
    
    # Create tester
    tester = ImageSearchAPITester(base_url, token)
    
    # Run tests
    print("\n" + "=" * 60)
    print("Running Tests...")
    print("=" * 60)
    
    # Test 1: Health Check
    tester.test_health_check()
    
    # Test 2: Authentication (only if not using token)
    if not token:
        tester.test_authentication()
    
    # Test 3: Search by File (requires a test image)
    test_image_path = "test_image.jpg"
    if Path(test_image_path).exists():
        tester.test_search_by_file(test_image_path)
    else:
        print(f"\n⊘ SKIP: Search by File (no test image at {test_image_path})")
    
    # Test 4: Search by URL
    test_image_url = "https://via.placeholder.com/200"
    if token:
        tester.test_search_by_url(test_image_url)
    
    # Test 5: Index Product (requires valid product ID)
    if token:
        tester.test_index_product(1, "https://via.placeholder.com/200")
    
    # Test 6: Batch Index
    if token:
        tester.test_batch_index()
    
    # Print summary
    tester.print_summary()
    
    # Exit with appropriate code
    sys.exit(0 if tester.results['failed'] == 0 else 1)


if __name__ == "__main__":
    main()
