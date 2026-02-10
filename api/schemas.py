from typing import List, Optional
from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    user_name: str
    user_role: str


class ServiceItem(BaseModel):
    area: str
    tipo: str
    qtd: int


class RegisterServiceRequest(BaseModel):
    veiculo_id: int
    quilometragem: int
    observacao: Optional[str] = None
    itens: List[ServiceItem]


class AllocationRequest(BaseModel):
    veiculo_id: int
    area: str
    box_id: int
    funcionario_id: int


class BoxServiceItem(BaseModel):
    area: str
    id: int
    quantidade: int


class BoxFinalizeRequest(BaseModel):
    obs_final: str | None = None
    servicos: List[BoxServiceItem]


class UpdateVehicleRequest(BaseModel):
    modelo: str | None = None
    ano_modelo: int | None = None
    nome_motorista: str | None = None
    contato_motorista: str | None = None


class UpdateClientRequest(BaseModel):
    nome_responsavel: str | None = None
    contato_responsavel: str | None = None


class CreateClientRequest(BaseModel):
    nome_empresa: str
    nome_fantasia: str | None = None


class LinkCompanyRequest(BaseModel):
    empresa: str
    cliente_id: int | None = None


class AddBoxServiceRequest(BaseModel):
    tipo: str
    quantidade: int = 1


class UpdateServiceTypeRequest(BaseModel):
    area: str
    tipo_atendimento: str


class RevertVisitRequest(BaseModel):
    veiculo_id: int
    quilometragem: int
