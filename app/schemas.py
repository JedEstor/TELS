from ninja import Schema
from typing import List, Optional


class CustomerIn(Schema):
    customer_name: str
    part_code: str
    tep_code: str
    part_name: str


class CustomerOut(Schema):
    id: int
    customer_name: str
    part_code: str
    tep_code: str
    part_name: str


class MaterialIn(Schema):
    maker: str
    material_part_code: str
    material_name: str
    unit: str         
    dim_qty: float
    loss_percent: Optional[float] = 10.0 
    total: float


class MaterialOut(Schema):
    id: int
    #customer_id: int
    maker: str
    material_part_code: str
    material_name: str
    unit: str
    dim_qty: float
    loss_percent: float
    total: float

class MaterialOut2(Schema):
    #id: int
    #customer_id: int

    maker: str
    material_part_code: str
    material_name: str
    unit: str
    dim_qty: float
    loss_percent: float
    total: float

class CustTrial(Schema):
    id: int
    customer_name: str
    part_code: str
    tep_code: str
    part_name: str

class CustomerWithMaterialsOut(Schema):
    id: int
    customer_name: str
    part_code: str
    tep_code: str
    part_name: str
    materials: List[MaterialOut]


"""

class CustomerIn(Schema):
    customer_name: str
    part_code: str


class CustomerOut(Schema):
    id: int
    customer_name: str
    part_code: str
   


class MaterialIn(Schema):
    tep_code: str
    maker: str
    material_part_code: str
    material_name: str
    unit: str         
    dim_qty: float
    loss_percent: Optional[float] = 10.0 
    total: float


class MaterialOut(Schema):
    id: int
    customer_id: int
    tep_code: str
    maker: str
    material_part_code: str
    material_name: str
    unit: str
    dim_qty: float
    loss_percent: float
    total: float

class CustomerWithMaterialsOut(Schema):
    id: int
    customer_name: str
    part_code: str
    tep_code: str
    materials: List[MaterialOut]
"""