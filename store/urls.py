from django.urls import path
from .views import (
    ProductListView, ProductDetailView, CreateProductView,
    CartView, AddToCartView, RemoveFromCartView, ProductDeleteView,
    FavouriteListView, AddFavouriteView, RemoveFavouriteView,
    ProductReviewListView, AddReviewView, PatchProductView
)

urlpatterns = [
    # Products
    path('products/', ProductListView.as_view(), name='product-list'),
    path('products/create/', CreateProductView.as_view(), name='create-product'),
    path('products/<slug:slug>/', ProductDetailView.as_view(), name='product-detail'),
    path('products/<slug:slug>/patch/', PatchProductView.as_view(), name='patch-product'),
    path("products/<slug:slug>/delete/", ProductDeleteView.as_view(), name="product-delete"),


    # Cart
    path('cart/', CartView.as_view(), name='cart-view'),
    path('cart/add/', AddToCartView.as_view(), name='add-to-cart'),
    path('cart/remove/<int:product_id>/', RemoveFromCartView.as_view(), name='remove-from-cart'),

    # Favourites
    path('favourites/', FavouriteListView.as_view(), name='favourites-list'),
    path('favourites/add/', AddFavouriteView.as_view(), name='add-favourite'),
    path('favourites/remove/<int:product_id>/', RemoveFavouriteView.as_view(), name='remove-favourite'),

    # Reviews
    path('products/<slug:slug>/reviews/', ProductReviewListView.as_view(), name='product-reviews'),
    path('products/<slug:slug>/review/add/', AddReviewView.as_view(), name='add-review'),
]
