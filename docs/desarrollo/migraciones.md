# Modelos y migraciones

## Crear un modelo

Cada modelo se define dentro de `backend/app/db/models/` y hereda de `Base`,
declarada en `backend/app/db/base.py`. Los campos y restricciones concretos
deben surgir del grooming y del modelo de dominio.

```python
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EntidadEjemplo(Base):
    __tablename__ = "entidades_ejemplo"
    __table_args__ = (
        CheckConstraint(
            "char_length(nombre) > 0",
            name="ck_entidades_ejemplo_nombre_no_vacio",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
```

Además del tipado, el modelo debe declarar claves foráneas, índices y
restricciones `NOT NULL`, `CHECK` o `UNIQUE` que representen invariantes
persistentes. Los estados y roles usan enums y los timestamps conservan la zona
horaria.

## Registrar la metadata

Alembic debe importar todos los módulos de modelos antes de asignar
`target_metadata`. Cuando existen varios modelos, sus importaciones se
centralizan en `backend/app/db/models/__init__.py` y `backend/alembic/env.py`
importa ese paquete.

```python
# Esta importación registra la tabla en Base.metadata.
from app.db.models import entidad_ejemplo  # noqa: F401
```

## Generar una revisión

Desde la raíz del repositorio, generar la migración con un nombre descriptivo.
En Linux o WSL se pasa el usuario anfitrión para evitar archivos propiedad de
`root`:

```bash
docker compose run --rm --user "$(id -u):$(id -g)" backend \
  alembic revision --autogenerate -m "create entidades ejemplo table"
```

Revisar manualmente el archivo creado en `backend/alembic/versions/`. Tanto
`upgrade()` como `downgrade()` deben ser viables y el autogenerado debe contener
las restricciones esperadas. Alembic no infiere con seguridad renombres,
conversiones de datos ni todos los cambios de enums.

No se modifica una migración que pueda haber sido aplicada por otra persona: se
crea una revisión correctiva.

## Aplicar y verificar

```bash
docker compose run --rm --build migrate
docker compose run --rm backend ruff check .
docker compose run --rm backend ruff format --check .
docker compose run --rm backend pytest
```

Si se verifica el `downgrade`, debe hacerse solamente sobre una base local
descartable. Las pruebas que dependen de enums, restricciones, transacciones o
locking se ejecutan contra PostgreSQL, no SQLite.
