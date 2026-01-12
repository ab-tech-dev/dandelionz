from django.db import models
from authentication.models import CustomUser
from users.models import Vendor
from django.utils.text import slugify
from django.utils import timezone
from cloudinary.models import CloudinaryField
import json



class Product(models.Model):
    CATEGORIES = [
        ('electronics', 'Electronics'),
        ('fashion', 'Fashion'),
        ('home_appliances', 'Home Appliances'),
        ('beauty', 'Beauty & Personal Care'),
        ('sports', 'Sports & Outdoors'),
        ('automotive', 'Automotive'),
        ('books', 'Books'),
        ('toys', 'Toys & Games'),
        ('groceries', 'Groceries'),
        ('computers', 'Computers & Accessories'),
        ('phones', 'Phones & Tablets'),
        ('jewelry', 'Jewelry & Watches'),
        ('baby', 'Baby Products'),
        ('pets', 'Pet Supplies'),
        ('office', 'Office Products'),
        ('gaming', 'Video Games & Consoles'),
    ]

    store = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='products')
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField()
    category = models.CharField(max_length=100, choices=CATEGORIES)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    discounted_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    stock = models.PositiveIntegerField()
    image = CloudinaryField('image', null=True, blank=True)
    brand = models.CharField(max_length=255, null=True, blank=True)
    tags = models.TextField(null=True, blank=True, help_text="Comma-separated tags or JSON array")
    variants = models.JSONField(null=True, blank=True, help_text="Product variants with color and/or size")
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
    customer = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='cart')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def total(self):
        return sum(item.subtotal for item in self.items.all())


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    @property
    def subtotal(self):
        return self.product.price * self.quantity


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
