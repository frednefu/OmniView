from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "mysql+pymysql://ipam:IpamDb2024!@localhost:13306/ipam"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "change-this-to-a-random-string"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440
    worker_token: str = "change-me-to-a-secure-random-string"
    cas_server_url: str = "https://cas.nefu.edu.cn/authserver"
    cas_service_url: str = "https://ov.nefu.edu.cn/api/auth/cas/callback"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
