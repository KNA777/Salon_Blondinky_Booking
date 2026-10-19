from pydantic import BaseModel


class MapperBase:
    schema: BaseModel = None
    model = None

    @classmethod
    def from_alchemy_to_schema(cls, data):
        return cls.schema.model_validate(data)

    @classmethod
    def from_schema_to_alchemy(cls, data):
        return cls.model(**data.model_dump())
