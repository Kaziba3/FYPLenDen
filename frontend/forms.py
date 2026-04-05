from django import forms

from .models import GoodsExchange, MoneyTransaction, UserProfile


class KYCForm(forms.ModelForm):
    dob = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    employment_type = forms.ChoiceField(
        choices=[
            ("SALARIED", "Salaried"),
            ("SELF_EMPLOYED", "Self Employed"),
            ("STUDENT", "Student"),
            ("BUSINESS", "Business Owners"),
            ("OTHER", "Other"),
        ]
    )

    class Meta:
        model = UserProfile
        fields = [
            "gender",
            "address",
            "aadhaar_number",
            "income_source",
            "monthly_income",
            "citizenship_front",
            "citizenship_back",
            "selfie",
            "income_proof",
        ]
        widgets = {
            "address": forms.Textarea(attrs={"rows": 3}),
        }


class LoanRequestForm(forms.ModelForm):
    deadline_days = forms.IntegerField(min_value=1, max_value=365)

    class Meta:
        model = MoneyTransaction
        fields = ["amount", "interest_rate"]

    def __init__(self, *args, **kwargs):
        self.borrower = kwargs.pop("borrower", None)
        super().__init__(*args, **kwargs)

    def clean_amount(self):
        amount = self.cleaned_data.get("amount")
        if self.borrower and amount:
            limit = self.borrower.profile.borrowing_limit
            if amount > limit:
                raise forms.ValidationError(
                    f"Amount exceeds your borrowing limit of {limit}"
                )
        return amount


class GoodsListingForm(forms.ModelForm):
    class Meta:
        model = GoodsExchange
        fields = ["item_name", "description", "exchange_type", "condition"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }
