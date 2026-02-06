#from django.contrib import admin

# Register your models here.

import json
from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError

from .models import Customer, Material


class CustomerAdminForm(forms.ModelForm):
    materials_json = forms.CharField(
        required=False,
        label="Materials (JSON)",
        widget=forms.Textarea(attrs={"rows": 18, "style": "font-family: monospace;"}),
    )

    class Meta:
        model = Customer
        fields = ("customer_name", "part_code", "tep_code")  

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.pk:
            materials = self.instance.materials.all().order_by("id")
            payload = [
                {
                    "maker": m.maker,
                    "material_part_code": m.material_part_code,
                    "material_name": m.material_name,
                    "unit": m.unit,
                    "dim_qty": m.dim_qty,
                    "loss_percent": m.loss_percent,
                    "total": m.total,
                }
                for m in materials
            ]
            self.fields["materials_json"].initial = json.dumps(payload, indent=2, ensure_ascii=False)

    def clean_materials_json(self):
        raw = self.cleaned_data.get("materials_json", "").strip()

        if raw == "":
            return []

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValidationError(f"Invalid JSON: {e}")

        if not isinstance(data, list):
            raise ValidationError("JSON must be an ARRAY (list) of materials.")

        allowed_units = {"pc", "pcs", "m"}

        for i, item in enumerate(data):
            if not isinstance(item, dict):
                raise ValidationError(f"Item #{i+1} must be an object/dict.")

            required = ["maker", "material_part_code", "material_name", "unit", "dim_qty", "total"]
            missing = [k for k in required if k not in item]
            if missing:
                raise ValidationError(f"Item #{i+1} missing keys: {', '.join(missing)}")

            if item["unit"] not in allowed_units:
                raise ValidationError(f"Item #{i+1}: unit must be one of {sorted(allowed_units)}")

            if "loss_percent" not in item or item["loss_percent"] in (None, ""):
                item["loss_percent"] = 10

            try:
                item["dim_qty"] = float(item["dim_qty"])
                item["loss_percent"] = float(item["loss_percent"])
                item["total"] = float(item["total"])
            except (TypeError, ValueError):
                raise ValidationError(f"Item #{i+1}: dim_qty/loss_percent/total must be numeric.")

        return data


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    form = CustomerAdminForm

    list_display = ("customer_name", "part_code", "tep_code", "materials_count")
    search_fields = ("customer_name", "tep_code", "part_code")

    inlines = []

    fields = ("customer_name", "part_code", "tep_code", "materials_json")

    def materials_count(self, obj: Customer):
        return obj.materials.count()
    materials_count.short_description = "Materials"

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)

        materials_data = form.cleaned_data.get("materials_json", [])

        Material.objects.filter(customer=obj).delete()

        for item in materials_data:
            Material.objects.create(
                customer=obj,
                maker=item["maker"],
                material_part_code=item["material_part_code"],
                material_name=item["material_name"],
                unit=item["unit"],
                dim_qty=item["dim_qty"],
                loss_percent=item.get("loss_percent", 10),
                total=item["total"],
            )


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = (
        "material_name",
        "material_part_code",
        "maker",
        "unit",
        "dim_qty",
        "loss_percent",
        "total",
        "customer",
    )
    #list_filter = ("unit", "maker")
    search_fields = ("material_name", "material_part_code", "maker", "customer__tep_code")
