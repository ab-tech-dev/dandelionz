from django.urls import path
from .views import (
    ProductListView, ProductDetailView, CreateProductView,
    CartView, AddToCartView, RemoveFromCartView, ProductDeleteView,
    FavouriteListView, AddFavouriteView, RemoveFavouriteView,
    ProductReviewListView, AddReviewView, PatchProductView,
    PendingProductsListView, ApproveProductView, RejectProductView, ApprovalStatsView,
    VendorDraftProductsView, SubmitDraftProductView, UpdateDraftProductView, DeleteDraftProductView,
    CategoryListCreateView, CategoryDetailView, ProductStatsView, ProductFilteredView,
    ProductSummaryView, ProductReviewView
)

urlpatterns = [
    # ==================
    # CATEGORIES
    # ==================
    path('categories/', CategoryListCreateView.as_view(), name='category-list-create'),
    path('categories/<slug:slug>/', CategoryDetailView.as_view(), name='category-detail'),

    # ==================
    # PRODUCTS - STATS & FILTERING
    # ==================
    path('products/stats/', ProductStatsView.as_view(), name='product-stats'),
    path('products/summary/', ProductSummaryView.as_view(), name='product-summary'),
    path('products/filtered/', ProductFilteredView.as_view(), name='product-filtered'),
    
    # ==================
    # PRODUCTS - CRUD
    # ==================
    path('products/', ProductListView.as_view(), name='product-list'),
    path('products/create/', CreateProductView.as_view(), name='create-product'),
    path('products/<slug:slug>/', ProductDetailView.as_view(), name='product-detail'),
    path('products/<slug:slug>/patch/', PatchProductView.as_view(), name='patch-product'),
    path("products/<slug:slug>/delete/", ProductDeleteView.as_view(), name="product-delete"),

    # ==================
    # CART
    # ==================
    path('cart/', CartView.as_view(), name='cart-view'),
    path('cart/add/', AddToCartView.as_view(), name='add-to-cart'),
    path('cart/remove/<slug:slug>/', RemoveFromCartView.as_view(), name='remove-from-cart'),

    # ==================
    # FAVOURITES
    # ==================
    path('favourites/', FavouriteListView.as_view(), name='favourites-list'),
    path('favourites/add/', AddFavouriteView.as_view(), name='add-favourite'),
    path('favourites/remove/<slug:slug>/', RemoveFavouriteView.as_view(), name='remove-favourite'),

    # ==================
    # REVIEWS
    # ==================
    path('products/<slug:slug>/reviews/', ProductReviewListView.as_view(), name='product-reviews'),
    path('products/<slug:slug>/review/add/', AddReviewView.as_view(), name='add-review'),

    # ==================
    # ADMIN - PRODUCT APPROVAL & REVIEW
    # ==================
    path('admin/products/pending/', PendingProductsListView.as_view(), name='pending-products'),
    path('admin/products/<slug:slug>/approve/', ApproveProductView.as_view(), name='approve-product'),
    path('admin/products/<slug:slug>/reject/', RejectProductView.as_view(), name='reject-product'),
    path('admin/products/<int:id>/review/', ProductReviewView.as_view(), name='product-review'),
    path('admin/products/stats/', ApprovalStatsView.as_view(), name='approval-stats'),

    # ==================
    # VENDOR - DRAFT PRODUCTS
    # ==================
    path('vendor/drafts/', VendorDraftProductsView.as_view(), name='vendor-drafts'),
    path('vendor/drafts/<slug:slug>/submit/', SubmitDraftProductView.as_view(), name='submit-draft'),
    path('vendor/drafts/<slug:slug>/update/', UpdateDraftProductView.as_view(), name='update-draft'),
    path('vendor/drafts/<slug:slug>/delete/', DeleteDraftProductView.as_view(), name='delete-draft'),
]
