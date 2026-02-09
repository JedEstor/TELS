#from django.db import models

# Create your models here.

   
from django.db import models
from django.core.exceptions import ValidationError

class Customer(models.Model):
    customer_name = models.CharField(max_length=120)

    parts = models.JSONField(default=list, blank=True)

    def __str__(self):
        return self.customer_name

    def clean(self):
        """
        Optional validation to keep parts JSON clean.
        """
        if self.parts in (None, ""):
            self.parts = []

        if not isinstance(self.parts, list):
            raise ValidationError({"parts": "parts must be a LIST of objects."})

        for i, item in enumerate(self.parts):
            if not isinstance(item, dict):
                raise ValidationError({"parts": f"parts[{i}] must be an object/dict."})

            if "Partcode" not in item or "Partname" not in item:
                raise ValidationError({"parts": f"parts[{i}] must contain Partcode and Partname."})

            if not str(item["Partcode"]).strip():
                raise ValidationError({"parts": f"parts[{i}].Partcode cannot be empty."})

            if not str(item["Partname"]).strip():
                raise ValidationError({"parts": f"parts[{i}].Partname cannot be empty."})


class TEPCode(models.Model):
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="tep_codes",
    )

    part_code = models.CharField(max_length=60)

    tep_code = models.CharField(max_length=60)

    class Meta:
        unique_together = ("customer", "part_code", "tep_code")

    def __str__(self):
        return f"{self.customer.customer_name} | {self.part_code} | {self.tep_code}"

"""
class MaterialList(models.Model):
   UNIT_CHOICES = [
       ("pc", "PC"),
       ("pcs", "PCS"),
       ("m", "M"),
   ]
    
   mat_partcode = models.CharField(max_length=80, unique=True)
   mat_partname = models. CharField(max_length=160)
   mat_maker = models.CharField(max_length=120)
   unit = models.CharField(max_length=10, choices=UNIT_CHOICES)
   default_dim_qty = models.FloatField(default=0)

   def __str__(self):
       return f"{self.mat_partname} ({self.mat_partcode})"
"""

"""class Material(models.Model):
    UNIT_CHOICES = [
        ("pc", "PC"),
        ("pcs", "PCS"),
        ("m", "M"),
    ]

    tep_code = models.ForeignKey(
        TEPCode,
        on_delete=models.CASCADE,
        related_name="materials",
    )

    material_ref = models.ForeignKey(
        MaterialList,
        on_delete=models.PROTECT,
        related_name="materials_used",
    )

    unit = models.CharField(max_length=10, choices=UNIT_CHOICES)
    dim_qty = models.FloatField()
    loss_percent = models.FloatField(default=10.0)
    total = models.FloatField()

    class Meta:
        unique_together = ("tep_code", "material_ref")

    def __str__(self):
        return f"{self.material_ref.mat_partname} ({self.material_ref.mat_partcode})"
"""
class Material(models.Model):
    UNIT_CHOICES = [
        ("pc", "PC"),
        ("pcs", "PCS"),
        ("m", "M"),
    ]

    tep_code = models.ForeignKey(
        TEPCode,
        on_delete=models.CASCADE,
        related_name="materials",
    )

    mat_partcode = models.CharField(max_length=80)
    mat_partname = models.CharField(max_length=160)
    mat_maker = models.CharField(max_length=120)

    unit = models.CharField(max_length=10, choices=UNIT_CHOICES)
    dim_qty = models.FloatField()
    loss_percent = models.FloatField(default=10.0)
    total = models.FloatField()

    def __str__(self):
        return f"{self.mat_partname} ({self.mat_partcode})"
    
# New syntax for the material list model.
class MaterialList(models.Model):
    UNIT_CHOICES = [
        ("pc", "PC"),
        ("pcs", "PCS"),
        ("m", "M"),
    ]

    mat_partcode = models.CharField(max_length=80, unique=True)
    mat_partname = models.CharField(max_length=160)
    mat_maker = models.CharField(max_length=120)
    unit = models.CharField(max_length=10, choices=UNIT_CHOICES)

    def __str__(self):
        return f"{self.mat_partname} ({self.mat_partcode})"


class CustomerCSV(models.Model):
    csv_file = models.FileField(upload_to="customer_csvs/")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"CustomerCSV {self.id}"


