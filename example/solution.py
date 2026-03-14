"""Spring PetClinic REST — localbox example solution.

A canonical Spring Boot REST API backed by PostgreSQL.
Source: https://github.com/spring-petclinic/spring-petclinic-rest

Quick start:
    cp solution-override.py.example solution-override.py
    # Edit solution-override.py and set db_password
    localbox clone projects
    localbox build projects
    localbox build services
    localbox compose generate
    docker compose up -d
    # API:     http://localhost:9966/petclinic/api/vets
    # Swagger: http://localhost:9966/petclinic/swagger-ui/index.html
"""
from dataclasses import dataclass

from localbox.models import (
    BaseEnv, env_field,
    SolutionConfig, JavaProject, maven,
    Service, DockerImage, ComposeConfig,
)
from localbox.models.builder import named_volume

@dataclass
class Env(BaseEnv):
    db_name: str = env_field()
    db_user: str = env_field()
    db_pass: str = env_field(is_secret=True)

config = SolutionConfig[Env](
    name="pet_clinic",
    env=Env(
        db_name = "pet_clinic",
        db_user = "pet_clinic",
    ),
)

# ── Project ───────────────────────────────────────────────────────────────────

pet_clinic = JavaProject(
    "pet_clinic",
    repo="https://github.com/spring-petclinic/spring-petclinic-rest.git",
    jdk=17,
    builder=maven("3.9"),
)

# ── Services ──────────────────────────────────────────────────────────────────

db = Service(
    name="db",
    image=DockerImage(image="postgres:16"),
    compose=ComposeConfig(
        order=1,
        environment={
            "POSTGRES_DB"      : config.env.db_name,
            "POSTGRES_USER"    : config.env.db_user,
            "POSTGRES_PASSWORD": config.env.db_pass,
        },
        volumes=named_volume("db_data", "/var/lib/postgresql/data"),
    ),
)

# Swagger UI will be available at http://localhost:9966/petclinic/swagger-ui/index.html
api = Service(
    name="api",
    project=pet_clinic,
    image=DockerImage(dockerfile="assets/Dockerfile"),
    compose=ComposeConfig(
        order=2,
        ports=["9966:9966"],
        depends_on=[db],
        environment={
            "SPRING_PROFILES_ACTIVE": "postgres,spring-data-jpa",
            "POSTGRES_URL":           f"jdbc:postgresql://{db.name}:5432/{config.env.db_name}",
            "POSTGRES_USER":          config.env.db_user,
            "POSTGRES_PASS":          config.env.db_pass,
        },
    ),
)
