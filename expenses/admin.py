from django.contrib import admin
from .models import Friend, Expense, ExpenseItem, ExpenseShare, Payment

# Inline for ExpenseItem related to Expense
class ExpenseItemInline(admin.TabularInline):
    model = ExpenseItem
    extra = 1  

# Inline for ExpenseShare related to Expense
class ExpenseShareInline(admin.TabularInline):
    model = ExpenseShare
    extra = 1  

@admin.register(Friend)
class FriendAdmin(admin.ModelAdmin):
    list_display = ('user', 'created_at', 'updated_at')
    search_fields = ('user__username',)

@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('title', 'total_amount', 'tax_amount', 'created_by', 'created_at') 
    search_fields = ('title', 'description', 'created_by__username')
    list_filter = ('created_at', 'created_by') 
    inlines = [ExpenseItemInline, ExpenseShareInline]  

@admin.register(ExpenseItem)
class ExpenseItemAdmin(admin.ModelAdmin):
    list_display = ('name', 'amount', 'expense', 'is_shared', 'assigned_to')
    search_fields = ('name', 'expense__title')
    list_filter = ('is_shared', 'assigned_to')  

@admin.register(ExpenseShare)
class ExpenseShareAdmin(admin.ModelAdmin):
    list_display = ('expense', 'participant', 'amount', 'paid_by', 'settled')
    search_fields = ('expense__title', 'participant__username')
    list_filter = ('paid_by', 'settled', 'participant')  

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('from_user', 'to_user', 'amount', 'created_at')
    search_fields = ('from_user__username', 'to_user__username', 'notes')
    list_filter = ('created_at', 'from_user', 'to_user')  