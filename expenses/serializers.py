from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Friend, Expense, ExpenseItem, ExpenseShare, Payment
from decimal import Decimal

import logging
logger = logging.getLogger(__name__)

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']

class FriendSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    total_balance = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    total_due_to_user = serializers.DecimalField(max_digits=10, decimal_places=2, source='get_total_due_to_user', read_only=True)
    total_user_owes = serializers.DecimalField(max_digits=10, decimal_places=2, source='get_total_user_owes', read_only=True)
    
    class Meta:
        model = Friend
        fields = ['id', 'user', 'total_balance', 'total_due_to_user', 'total_user_owes', 'created_at', 'updated_at']

class ExpenseItemSerializer(serializers.ModelSerializer):
    assigned_to = UserSerializer(read_only=True)
    assigned_to_id = serializers.IntegerField(
        write_only=True, required=False, allow_null=True
    )

    class Meta:
        model = ExpenseItem
        fields = ['id', 'name', 'amount', 'is_shared', 'assigned_to', 'assigned_to_id']

    def validate(self, data):
        if not data.get("is_shared", True) and data.get("assigned_to_id") is None:
            raise serializers.ValidationError({
                "assigned_to_id": "This field is required for non-shared items."
            })
        return data

class ExpenseShareSerializer(serializers.ModelSerializer):
    participant = UserSerializer(read_only=True)
    participant_id = serializers.IntegerField(write_only=True)
    
    class Meta:
        model = ExpenseShare
        fields = ['id', 'participant', 'participant_id', 'amount', 'paid_by', 'settled']

class ExpenseSerializer(serializers.ModelSerializer):
    created_by = UserSerializer(read_only=True)
    items = ExpenseItemSerializer(many=True)
    shares = ExpenseShareSerializer(many=True, read_only=True)
    participants = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        many=True,
        write_only=True
    )
    
    class Meta:
        model = Expense
        fields = ['id', 'title', 'description', 'total_amount', 'tax_amount', 'created_by', 'items', 'shares', 'participants', 'created_at', 'updated_at']
    
    def create(self, validated_data):
        logger.debug("Expense create validated_data: %s", validated_data)
        items_data = validated_data.pop('items')
        participants = validated_data.pop('participants')
        
        # Create the expense with the tax_amount included
        request_user = self.context['request'].user
        # Only add request_user if not already in participants
        if request_user.id not in [p.id for p in participants]:
            participants.append(request_user)
        expense = Expense.objects.create(**validated_data)
        
        # Create expense items
        total_items_amount = Decimal('0.00')
        for item_data in items_data:
            try:
                item = ExpenseItem.objects.create(expense=expense, **item_data)
                total_items_amount += item.amount
            except Exception as e:
                logger.error("Error creating ExpenseItem with data %s: %s", item_data, e)
                raise e
        
        # Validate total amount matches items total
        if expense.total_amount != total_items_amount:
            logger.warning(
                "Total amount (%s) doesn't match sum of items (%s)",
                expense.total_amount,
                total_items_amount
            )
        
        # Calculate shares
        self._calculate_shares(expense, participants)
        
        return expense
    
    def _calculate_shares(self, expense, participants):
        # Get all items for this expense
        items = expense.items.all()
        payer = expense.created_by
        
        # Dictionary to accumulate each participant's share
        participant_shares = {user.id: Decimal('0.00') for user in participants}
        
        # Process each expense item
        for item in items:
            if item.is_shared:
                # Split equally among all participants
                share_amount = item.amount / len(participants)
                for participant in participants:
                    participant_shares[participant.id] += share_amount
            elif item.assigned_to:
                # Non-shared: assign full amount to assigned person
                participant_shares[item.assigned_to.id] += item.amount
        
        # Add tax equally among participants (if tax_amount is provided)
        if expense.tax_amount and expense.tax_amount > 0:
            tax_share = expense.tax_amount / len(participants)
            for participant in participants:
                participant_shares[participant.id] += tax_share
        
        # Create ExpenseShare records based on calculated shares
        created_shares = []
        for participant in participants:
            share_amount = participant_shares[participant.id]
            if share_amount > 0:
                # Create share for participant if they're not the payer
                if participant != payer:
                    share = ExpenseShare.objects.create(
                        expense=expense,
                        participant=participant,
                        amount=share_amount,
                        paid_by=False,
                        settled=False
                    )
                    created_shares.append(share)
                
                # Create share for payer to track what others owe
                if participant != payer:
                    share = ExpenseShare.objects.create(
                        expense=expense,
                        participant=payer,
                        amount=share_amount,
                        paid_by=True,
                        settled=False
                    )
                    created_shares.append(share)

class PaymentSerializer(serializers.ModelSerializer):
    from_user = UserSerializer(read_only=True)
    to_user = UserSerializer(read_only=True)
    from_user_id = serializers.IntegerField(write_only=True)
    to_user_id = serializers.IntegerField(write_only=True)
    
    class Meta:
        model = Payment
        fields = ['id', 'from_user', 'to_user', 'from_user_id', 'to_user_id', 'amount', 'notes', 'created_at']
    
    def create(self, validated_data):
        payment = Payment.objects.create(**validated_data)
        
        # Get all unsettled expense shares
        unsettled_shares = ExpenseShare.objects.filter(
            participant=payment.from_user,
            expense__created_by=payment.to_user,
            paid_by=False,
            settled=False
        ).order_by('expense__created_at')  # Process oldest expenses first
        
        remaining_amount = payment.amount
        
        # Settle expenses partially or fully based on payment amount
        for share in unsettled_shares:
            if remaining_amount <= 0:
                break
                
            if remaining_amount >= share.amount:
                # Can settle this expense fully
                share.settled = True
                share.save()
                remaining_amount -= share.amount
            else:
                # Can only settle partially - create a new share for remaining amount
                settled_amount = remaining_amount
                remaining_debt = share.amount - settled_amount
                
                # Update original share amount
                share.amount = remaining_debt
                share.save()
                
                # Create a new share for the settled portion
                ExpenseShare.objects.create(
                    expense=share.expense,
                    participant=share.participant,
                    amount=settled_amount,
                    paid_by=False,
                    settled=True
                )
                
                remaining_amount = 0
                break
        
        return payment