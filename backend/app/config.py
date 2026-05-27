from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "mysql+pymysql://ipam:IpamDb2024!@localhost:3306/ipam"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "change-this-to-a-random-string"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480
    worker_token: str = "change-me-to-a-secure-random-string"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
