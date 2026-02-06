#from django.db import models

# Create your models here.
from django.db import models

# Create your models here.

class Customer(models.Model):
    customer_name = models.CharField(max_length=120)
    part_code = models.CharField(max_length=60)
    tep_code = models.CharField(max_length=60) 
    part_name = models.CharField(max_length=120)

    def __str__(self):
        return f"{self.customer_name} ({self.tep_code})"


class Material(models.Model):
    UNIT_CHOICES = [
        ("pc", "pc"),
        ("pcs", "pcs"),
        ("m", "m"),
    ]

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="materials") #magging base sa tep_code

    maker = models.JSONField(default=dict)
    material_part_code = models.CharField(max_length=80)
    material_name = models.CharField(max_length=160, blank=True, null=True) 



    unit = models.CharField(max_length=10, choices=UNIT_CHOICES)   
    dim_qty = models.FloatField()                                  
    loss_percent = models.FloatField(default=10.0)                 
    total = models.FloatField()

    def __str__(self):
        return f"{self.material_name} - {self.material_part_code}"
