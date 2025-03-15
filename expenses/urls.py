from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from . import auth

router = DefaultRouter()
router.register(r'users', views.UserViewSet)
router.register(r'friends', views.FriendViewSet, basename='friend')
router.register(r'expenses', views.ExpenseViewSet)
router.register(r'expense-items', views.ExpenseItemViewSet)
router.register(r'expense-shares', views.ExpenseShareViewSet)
router.register(r'payments', views.PaymentViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('auth/register/', auth.register_user, name='register'),
    path('auth/login/', auth.login_user, name='login'),
    path('auth/logout/', auth.logout_user, name='logout'),
]