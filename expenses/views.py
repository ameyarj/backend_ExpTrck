from decimal import Decimal
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.contrib.auth.models import User
from django.db.models import Sum, Q, F
from .models import Friend, Expense, ExpenseItem, ExpenseShare, Payment
from .serializers import (
    UserSerializer, FriendSerializer, ExpenseSerializer,
    ExpenseItemSerializer, ExpenseShareSerializer, PaymentSerializer
)
import logging
logger = logging.getLogger(__name__)

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def me(self, request):
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)

class FriendViewSet(viewsets.ModelViewSet):
    serializer_class = FriendSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        # Only return users who have shared expenses with the current user
        return User.objects.filter(
            Q(expenses__shares__participant=self.request.user) |
            Q(expense_shares__expense__created_by=self.request.user)
        ).distinct().exclude(id=self.request.user.id)
    
    @action(detail=True, methods=['get'])
    def balance(self, request, pk=None):
        try:
            friend = User.objects.get(pk=pk)
            current_user = request.user
            
            # Calculate what friend owes to current user
            due_to_user = ExpenseShare.objects.filter(
                expense__created_by=current_user,
                participant=friend,
                paid_by=False,
                settled=False
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
            
            # Calculate what current user owes to friend
            user_owes = ExpenseShare.objects.filter(
                expense__created_by=friend,
                participant=current_user,
                paid_by=False,
                settled=False
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
            
            data = {
                'total_balance': due_to_user - user_owes,
                'total_due_to_user': due_to_user,
                'total_user_owes': user_owes
            }
            return Response(data)
        except User.DoesNotExist:
            return Response(
                {"error": "Friend not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error calculating balance: {str(e)}")
            return Response(
                {"error": "Failed to calculate balance"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get'])
    def overall_balance(self, request):
        user = request.user
        # Total amount others owe the user
        due_to_user = ExpenseShare.objects.filter(
            expense__created_by=user,
            paid_by=False,
            settled=False
        ).exclude(
            participant=user
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        
        # Total amount the user owes others
        user_owes = ExpenseShare.objects.filter(
            participant=user,
            paid_by=False,
            settled=False
        ).exclude(
            expense__created_by=user
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        
        # Friends who owe the user
        friends_owing_user = ExpenseShare.objects.filter(
            expense__created_by=user,
            paid_by=False,
            settled=False
        ).exclude(
            participant=user
        ).values('participant').annotate(
            total=Sum('amount'),
            username=F('participant__username')
        )
        
        # Friends the user owes
        user_owing_friends = ExpenseShare.objects.filter(
            participant=user,
            paid_by=False,
            settled=False
        ).exclude(
            expense__created_by=user
        ).values('expense__created_by').annotate(
            total=Sum('amount'),
            username=F('expense__created_by__username')
        )
        
        data = {
            'total_balance': due_to_user - user_owes,
            'total_due_to_user': due_to_user,
            'total_user_owes': user_owes,
            'friends_owing_user': list(friends_owing_user),
            'user_owing_friends': list(user_owing_friends),
        }
        return Response(data)

class ExpenseViewSet(viewsets.ModelViewSet):
    queryset = Expense.objects.all()
    serializer_class = ExpenseSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def perform_create(self, serializer):
        logger.debug("Incoming expense creation request data: %s", self.request.data)
        serializer.save(created_by=self.request.user)
    
    def get_queryset(self):
        user = self.request.user
        return Expense.objects.filter(
            Q(created_by=user) | Q(shares__participant=user)
        ).distinct()
    
    @action(detail=False, methods=['get'])
    def my_expenses(self, request):
        expenses = Expense.objects.filter(created_by=request.user)
        serializer = self.get_serializer(expenses, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def friend_expenses(self, request):
        friend_id = request.query_params.get('friend_id')
        if not friend_id:
            return Response(
                {"error": "friend_id is required"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            friend = User.objects.get(pk=friend_id)
            # Get expenses where both users are participants
            expenses = Expense.objects.filter(
                (Q(created_by=friend) & Q(shares__participant=request.user)) |
                (Q(created_by=request.user) & Q(shares__participant=friend))
            ).distinct()
            
            if not expenses.exists():
                return Response([])
                
            serializer = self.get_serializer(expenses, many=True)
            return Response(serializer.data)
        except User.DoesNotExist:
            return Response(
                {"error": "Friend not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )

class ExpenseItemViewSet(viewsets.ModelViewSet):
    queryset = ExpenseItem.objects.all()
    serializer_class = ExpenseItemSerializer
    permission_classes = [permissions.IsAuthenticated]

class ExpenseShareViewSet(viewsets.ModelViewSet):
    queryset = ExpenseShare.objects.all()
    serializer_class = ExpenseShareSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        return ExpenseShare.objects.filter(
            Q(participant=user) | Q(expense__created_by=user)
        )

class PaymentViewSet(viewsets.ModelViewSet):
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def perform_create(self, serializer):
        serializer.save(from_user=self.request.user)
    
    def get_queryset(self):
        user = self.request.user
        return Payment.objects.filter(
            Q(from_user=user) | Q(to_user=user)
        )