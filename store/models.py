from django.db import models
from django.db.models import Sum, Count
from authentication.models import CustomUser
from users.models import Vendor
from django.utils.text import slugify
from django.utils import timezone
from cloudinary.models import CloudinaryField
import json
import uuid


# ==========================================
# Category Model
# ==========================================
class Category(models.Model):
    """
    Represents a product category with aggregated metrics.
    """
    name = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField(blank=True, null=True)
    image = CloudinaryField('image', null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ['name']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    @property
    def product_count(self):
        """Get count of approved products in this category"""
        return self.products.filter(approval_status='approved', publish_status='submitted').count()

    @property
    def total_sales(self):
        """Get total sales value from all orders of products in this category"""
        from transactions.models import Order, OrderItem
        total = OrderItem.objects.filter(
            product__category=self,
            product__approval_status='approved'
        ).aggregate(total=Sum('quantity'))['total'] or 0
        return total

    def __str__(self):
        return self.name


class Product(models.Model):
    APPROVAL_STATUS = [
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    PUBLISH_STATUS = [
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
    ]

    # UUID for external API references (like orders do)
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    
    store = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='products')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='products')
    name = models.CharField(max_length=255, blank=True)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    discounted_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    stock = models.PositiveIntegerField(null=True, blank=True)
    brand = models.CharField(max_length=255, null=True, blank=True)
    tags = models.TextField(null=True, blank=True, help_text="Comma-separated tags or JSON array")
    variants = models.JSONField(null=True, blank=True, help_text="Product variants with color and/or size")
    
    # Draft & Publish Status
    publish_status = models.CharField(max_length=20, choices=PUBLISH_STATUS, default='draft')
    
    # Approval fields
    approval_status = models.CharField(max_length=20, choices=APPROVAL_STATUS, default='pending')
    approved_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_products')
    approval_date = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            num = 1
            while Product.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{num}"
                num += 1
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def in_stock(self):
        return self.stock > 0

    def __str__(self):
        return self.name

    @property
    def has_main_image(self):
        """Check if product has at least one main image"""
        return self.images.filter(is_main=True).exists()

    @property
    def main_image(self):
        """Get the main image for this product"""
        return self.images.filter(is_main=True).first()

    @property
    def all_images(self):
        """Get all images for this product, ordered by is_main first, then created_at"""
        return self.images.all().order_by('-is_main', 'created_at')

    @property
    def video(self):
        """Get the main video for this product"""
        return self.videos.first()


# ==========================================
# Product Image Model
# ==========================================
class ProductImage(models.Model):
    """
    Represents a product image with optional variant association.
    Each image can be associated with specific variants (colors/sizes).
    """
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    image = CloudinaryField('image', null=False, blank=False)
    is_main = models.BooleanField(default=False, help_text="Main/primary image for product display")
    alt_text = models.CharField(max_length=255, null=True, blank=True, help_text="Alternative text for accessibility")
    
    # Variant association - JSON field for flexibility
    # e.g., {"colors": ["red", "blue"], "sizes": ["M", "L"]}
    variant_association = models.JSONField(
        null=True, 
        blank=True, 
        default=None,
        help_text="JSON mapping of variant attributes (e.g., {\"colors\": [\"red\", \"blue\"]}). Leave null/empty for all variants."
    )
    
    display_order = models.PositiveIntegerField(default=0, help_text="Order in which to display images")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_main', 'display_order', 'uploaded_at']

    def __str__(self):
        return f"{'Main ' if self.is_main else ''}Image for {self.product.name}"

    def save(self, *args, **kwargs):
        # If this is being set as main, unset others
        if self.is_main:
            ProductImage.objects.filter(product=self.product, is_main=True).exclude(pk=self.pk).update(is_main=False)
        super().save(*args, **kwargs)


# ==========================================
# Product Video Model
# ==========================================
class ProductVideo(models.Model):
    """
    Represents a product video (optional).
    Max file size is 5MB.
    """
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='videos')
    video = CloudinaryField('video', null=False, blank=False, resource_type='video')
    title = models.CharField(max_length=255, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    
    # Metadata
    duration = models.PositiveIntegerField(null=True, blank=True, help_text="Video duration in seconds")
    file_size = models.PositiveIntegerField(null=True, blank=True, help_text="File size in bytes")
    
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"Video for {self.product.name}"


# -------------------------------
# Cart & Related Models
# -------------------------------
class Cart(models.Model):
    customer = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='cart', help_text="Each customer has one active cart")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # Ensure one cart per customer
        constraints = [
            models.UniqueConstraint(fields=['customer'], name='one_cart_per_customer')
        ]

    @property
    def total(self):
        return sum(item.subtotal for item in self.items.all())
    
    def __str__(self):
        return f"Cart for {self.customer.email}"


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        # Prevent duplicate products in same cart
        unique_together = ('cart', 'product')

    @property
    def subtotal(self):
        """Calculate item subtotal using discounted price if available, else regular price"""
        price = self.product.discounted_price if self.product.discounted_price else self.product.price
        return price * self.quantity if price else 0


class Favourite(models.Model):
    customer = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='favourites')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='favourited_by')
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('customer', 'product')

    def __str__(self):
        return f"{self.customer.full_name or self.customer.email} favourited {self.product.name}"


class Review(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='reviews')
    customer = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='reviews')
    rating = models.PositiveIntegerField(default=1)
    comment = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Review for {self.product.name} by {self.customer.email}"


# ==========================================
# Product Media Helper Functions
# ==========================================
def validate_video_size(file_size_bytes, max_size_mb=5):
    """
    Validate video file size.
    
    Args:
        file_size_bytes: Size of file in bytes
        max_size_mb: Maximum allowed size in MB (default 5MB)
    
    Returns:
        tuple: (is_valid: bool, error_message: str or None)
    """
    max_size_bytes = max_size_mb * 1024 * 1024
    if file_size_bytes > max_size_bytes:
        return False, f"Video size exceeds {max_size_mb}MB limit"
    return True, None


def validate_variant_association(variant_association, product_variants):
    """
    Validate that provided variant association exists in product variants.
    
    Args:
        variant_association: JSON object with variant attributes
        product_variants: Product's variants JSON field
    
    Returns:
        tuple: (is_valid: bool, error_message: str or None)
    """
    if not variant_association or not product_variants:
        return True, None  # No association or no product variants is valid
    
    # Ensure both are dicts
    if not isinstance(variant_association, dict) or not isinstance(product_variants, dict):
        return False, "Invalid variant format"
    
    for key, values in variant_association.items():
        if key not in product_variants:
            return False, f"Variant key '{key}' not found in product variants"
        
        product_variant_values = product_variants.get(key, [])
        if isinstance(values, list):
            for val in values:
                if val not in product_variant_values:
                    return False, f"Variant value '{val}' not found in product {key} variants"
    
    return True, None

