from django.db import models
from django.contrib.auth.models import User
from django.db.models import Sum, F, Q
from decimal import Decimal

class Friend(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.user.username
    
    def total_balance(self):
        """Calculate the total balance (amount due to the user - amount owed by the user)"""
        due_to_user = self.get_total_due_to_user()
        user_owes = self.get_total_user_owes()
        return due_to_user - user_owes
    
    def get_total_due_to_user(self):
        """Calculate the total amount due to the user"""
        return ExpenseShare.objects.filter(
            expense__created_by=self.user,
            paid_by=False,
            settled=False
        ).exclude(
            participant=self.user
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    def get_total_user_owes(self):
        """Calculate the total amount the user owes to others"""
        return ExpenseShare.objects.filter(
            participant=self.user,
            paid_by=False,  # Changed from True to False
            settled=False
        ).exclude(
            expense__created_by=self.user
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    def get_friends_owing_user(self):
        """Get a list of friends who owe money to the user"""
        return ExpenseShare.objects.filter(
            expense__created_by=self.user,
            paid_by=False,
            settled=False
        ).exclude(
            participant=self.user
        ).values('participant').annotate(
            total=Sum('amount'),
            username=F('participant__username')
        )
    
    def get_user_owing_friends(self):
        """Get a list of friends to whom the user owes money"""
        return ExpenseShare.objects.filter(
            participant=self.user,
            paid_by=False,  # Changed from True to False
            settled=False
        ).exclude(
            expense__created_by=self.user
        ).values('expense__created_by').annotate(
            total=Sum('amount'),
            username=F('expense__created_by__username')
        )

class Expense(models.Model):
    title = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)  # New tax field
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='expenses')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.title} - {self.total_amount}"

class ExpenseItem(models.Model):
    expense = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name='items')
    name = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    is_shared = models.BooleanField(default=True)
    assigned_to = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    
    def __str__(self):
        return f"{self.name} - {self.amount}"

class ExpenseShare(models.Model):
    expense = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name='shares')
    participant = models.ForeignKey(User, on_delete=models.CASCADE, related_name='expense_shares')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    paid_by = models.BooleanField(default=False) 
    settled = models.BooleanField(default=False)
    
    def __str__(self):
        action = "paid" if self.paid_by else "owes"
        return f"{self.participant.username} {action} {self.amount} for {self.expense.title}"

class Payment(models.Model):
    from_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payments_made')
    to_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payments_received')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.from_user.username} paid {self.amount} to {self.to_user.username}"