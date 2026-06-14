import os
import sys
import argparse
import django

# Set Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

try:
    django.setup()
except Exception as e:
    print(f"Error initializing Django: {e}", file=sys.stderr)
    sys.exit(1)

from django.core.management import call_command

def main():
    parser = argparse.ArgumentParser(description="Calculate product associations using the Apriori algorithm.")
    parser.add_argument(
        '--min-support',
        type=int,
        default=2,
        help='Minimum number of times a product pair must be bought together (default: 2)'
    )
    args = parser.parse_args()

    print(f"Starting product association calculation (min-support: {args.min_support})...")
    try:
        call_command('run_product_association', min_support=args.min_support)
        print("Product association calculation completed successfully.")
    except Exception as e:
        print(f"Error during calculation: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
