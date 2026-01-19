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
    image = CloudinaryField('image', null=True, blank=True)
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
