from django.core.management.base import BaseCommand
from django.db import transaction
from api.models import Invoice, Purchase, Product, ProductAssociation
import collections
from decimal import Decimal

class Command(BaseCommand):
    help = 'Run Apriori algorithm to compute product associations based on invoice data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--min-support',
            type=int,
            default=2,
            help='Minimum number of times a product pair must be bought together to be considered'
        )

    def handle(self, *args, **options):
        min_support = options['min_support']
        self.stdout.write(f'Running product association with min-support={min_support}...')

        # Step 1: Fetch all paid or pending invoices and their purchases
        invoices = Invoice.objects.filter(status__in=['Paid', 'Pending']).prefetch_related('purchases')
        
        self.stdout.write(f'Found {invoices.count()} paid/pending invoices.')

        # Step 2: Map invoices to set of products
        invoice_products = collections.defaultdict(set)
        for invoice in invoices:
            for purchase in invoice.purchases.all():
                if purchase.product_id is not None:
                    invoice_products[invoice.invoiceId].add(purchase.product_id)

        # Step 3: Count total purchases (invoices containing the product) for each product
        total_purchases = collections.defaultdict(int)
        for inv_id, prods in invoice_products.items():
            for prod in prods:
                total_purchases[prod] += 1

        # Step 4: Count product pair occurrences
        pair_frequencies = collections.defaultdict(int)
        for inv_id, prods in invoice_products.items():
            prod_list = sorted(list(prods))
            for i, prod_a in enumerate(prod_list):
                for prod_b in prod_list[i+1:]:
                    pair_frequencies[(prod_a, prod_b)] += 1

        # Step 5: Filter pairs by min_support and prepare associations for bulk creation
        associations_to_create = []
        skipped_pairs = 0
        created_pairs = 0

        # Pre-fetch products to make sure they exist and map them
        all_product_ids = set(total_purchases.keys())
        products_map = {p.productId: p for p in Product.objects.filter(productId__in=all_product_ids)}

        for (prod_a_id, prod_b_id), freq in pair_frequencies.items():
            if freq < min_support:
                skipped_pairs += 1
                continue

            prod_a = products_map.get(prod_a_id)
            prod_b = products_map.get(prod_b_id)

            if not prod_a or not prod_b:
                continue

            # Confidence(A -> B) = freq(A, B) / total(A) * 100
            total_a = total_purchases[prod_a_id]
            pct_a = min((freq / total_a) * 100.0, 100.0) if total_a > 0 else 0.0

            # Confidence(B -> A) = freq(A, B) / total(B) * 100
            total_b = total_purchases[prod_b_id]
            pct_b = min((freq / total_b) * 100.0, 100.0) if total_b > 0 else 0.0

            # Create A -> B
            associations_to_create.append(ProductAssociation(
                product1=prod_a,
                product2=prod_b,
                frequency=freq,
                totalProduct1Purchases=total_a,
                associationPercentage=Decimal(f"{pct_a:.2f}")
            ))

            # Create B -> A
            associations_to_create.append(ProductAssociation(
                product1=prod_b,
                product2=prod_a,
                frequency=freq,
                totalProduct1Purchases=total_b,
                associationPercentage=Decimal(f"{pct_b:.2f}")
            ))
            
            created_pairs += 1

        # Step 6: Atomic delete of old associations and insert of new ones
        with transaction.atomic():
            deleted_count, _ = ProductAssociation.objects.all().delete()
            self.stdout.write(f'Deleted {deleted_count} stale product association(s).')
            
            ProductAssociation.objects.bulk_create(associations_to_create)
            self.stdout.write(f'Successfully created {len(associations_to_create)} product association(s) ({created_pairs} pairs).')

        self.stdout.write(self.style.SUCCESS('Product association computation completed.'))
