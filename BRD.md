# Localbox - Local Development Environment Orchestration

## Technical Requirements Document

**Version:** 1.0
**Last Updated:** 2026-02-04

> **Note:** This is the original requirements document. The implementation has moved from
> Gradle to a Python CLI tool (`src/localbox/`). Sections 11 (Implementation Alternatives)
> and 13 (Service Onboarding Guide) reference the old Gradle approach and are kept for
> historical context. See `README.md` and `localdev/python-localbox.md` for current
> implementation details.

---

## 1. Overview

### 1.1 Purpose

Localbox is a local development environment orchestration system that manages multiple interconnected services via Docker Compose. It provides a unified interface for building, deploying, and managing services during local development.

### 1.2 Goals

- Simplify local development setup for a multi-service architecture
- Provide independent control over each service (start, stop, build, logs)
- Manage service dependencies automatically
- Support multiple service types (databases, Tomcat, SpringBoot, frontend)
- Enable incremental builds and selective service deployment
- Generate Docker Compose configurations dynamically

### 1.3 Non-Goals

- Production deployment
- CI/CD pipeline management
- Cloud infrastructure provisioning

---

## 2. System Architecture

### 2.1 Service Categories

| Category       | Description                      | Container Runtime     |
|----------------|----------------------------------|-----------------------|
| **Database**   | PostgreSQL instances             | postgres:14           |
| **Tomcat**     | Java WAR applications (JDK 8/17) | tomcat:9.0-jdk8/jdk17 |
| **SpringBoot** | Java JAR applications (JDK 21)   | amazoncorretto:21     |
| **Frontend**   | Static files served by Nginx     | nginx:latest          |

### 2.2 Services Inventory

#### 2.2.1 Database Services

| Service ID  | Description               | Default Port | Persistent Volume |
|-------------|---------------------------|--------------|-------------------|
| `db-main`   | Main application database | 5432         | db-main-data      |
| `db-shared` | Shared/common database    | 5433         | db-shared-data    |

#### 2.2.2 Backend Library Projects (Build Only)

These projects produce Maven artifacts used by other services. They do not run as containers.

| Project ID           | Repository         | JDK Version | Produces               |
|----------------------|--------------------|-------------|------------------------|
| `utils`              | utils              | 8           | JAR (Maven dependency) |
| `security-prototype` | security-prototype | 8           | JAR + WAR (authserver) |
| `fs-s3-storage`      | fs-s3-storage      | 8           | WAR (s3)               |
| `vix12parser`        | vix12parser        | 8           | JAR (Maven dependency) |

#### 2.2.3 Tomcat Services

| Service ID        | Repository         | JDK Version | WAR Source                                | Default Port |
|-------------------|--------------------|-------------|-------------------------------------------|--------------|
| `authserver`      | security-prototype | 8           | auth-server/target/oauth2-auth-server.war | 8081         |
| `communication`   | communication      | 8           | target/Communication-1.0-SNAPSHOT.war     | 8082         |
| `lookup`          | lookup             | 8           | target/Lookup-1.0-SNAPSHOT.war            | 8083         |
| `s3`              | fs-s3-storage      | 8           | target/fs-s3-storage-1.0-SNAPSHOT.war     | 8084         |
| `processor`       | processor          | 8           | target/Processor-1.0-SNAPSHOT.war         | 8085         |
| `employer-portal` | employer-portal    | **17**      | target/employer-portal-2.0.war            | 8086         |

#### 2.2.4 SpringBoot Services

| Service ID          | Repository        | JDK Version | Build System    | Default Port |
|---------------------|-------------------|-------------|-----------------|--------------|
| `remittance-engine` | remittance-engine | 21          | Gradle or Maven | 8090         |

#### 2.2.5 Frontend Services

| Service ID           | Repository         | Build Tool            | Default Ports  |
|----------------------|--------------------|-----------------------|----------------|
| `fe` (nginx)         | -                  | -                     | 80, 9001, 9002 |
| `ui`                 | ui                 | Node.js (bower/grunt) | -              |
| `viveka-ui`          | viveka-ui          | Node.js (npm)         | -              |
| `employer-portal-ui` | employer-portal-ui | Node.js (npm)         | -              |

---

## 3. Service Dependencies

### 3.1 Runtime Dependencies (Docker Compose)

Services must start in dependency order. A service cannot start until its dependencies are healthy.

```
db-main ─────────────────────────────────────────────┐
    │                                                 │
    ├── authserver                                    │
    │       │                                         │
    │       ├── communication ────────┐               │
    │       │                         │               │
    │       ├── lookup                │               │
    │       │                         │               │
    │       ├── s3                    │               │
    │       │                         │               │
    │       ├── employer-portal       │               │
    │       │                         ▼               │
db-shared ──┴── processor ◄───────────┘               │
    │              │                                  │
    │              │                                  │
    └──────────────┴── remittance-engine              │
                                                      │
fe (nginx) ◄── authserver, processor, employer-portal │
```

### 3.2 Dependency Matrix

| Service             | Depends On                                    |
|---------------------|-----------------------------------------------|
| `authserver`        | db-main                                       |
| `communication`     | db-main, authserver                           |
| `lookup`            | db-main, authserver                           |
| `s3`                | db-main, authserver                           |
| `processor`         | db-main, db-shared, authserver, communication |
| `employer-portal`   | db-main, authserver                           |
| `remittance-engine` | db-main, db-shared, authserver                |
| `fe`                | authserver, processor, employer-portal        |

### 3.3 Build Dependencies (Maven/Gradle)

Library projects must be built before dependent services.

```
utils
  ├── security-prototype
  ├── fs-s3-storage
  ├── vix12parser
  │       └── communication
  │             └── processor
  ├── lookup
  └── employer-portal
```

---

## 4. Required Operations

### 4.1 Command Structure

The system must support the following command patterns:

```
<tool> [:<category>][:<service>]:<action> [options]
```

Examples:
```
<tool> start                        # Start all services
<tool> :db:start                    # Start all databases
<tool> :db:main:start               # Start main database only
<tool> :be:tomcat:processor:build   # Build processor service
<tool> :be:springboot:start         # Start all SpringBoot services
```

### 4.2 Actions by Category

#### 4.2.1 Global Actions

| Action            | Description                                  |
|-------------------|----------------------------------------------|
| `start`           | Start all services (respecting dependencies) |
| `stop`            | Stop all services                            |
| `status`          | Show status of all services                  |
| `logs`            | Follow logs for all services                 |
| `clone`           | Clone all git repositories                   |
| `fetch`           | Pull latest from all repositories            |
| `buildAll`        | Build all services                           |
| `generateCompose` | Generate all docker-compose files            |
| `config`          | Display current configuration                |

#### 4.2.2 Database Actions

| Action            | Description                      |
|-------------------|----------------------------------|
| `start`           | Start database container         |
| `stop`            | Stop database container          |
| `logs`            | Follow database logs             |
| `shell`           | Open psql shell to database      |
| `generateCompose` | Generate docker-compose fragment |

#### 4.2.3 Backend Service Actions

| Action                   | Description                      |
|--------------------------|----------------------------------|
| `clone`                  | Clone git repository             |
| `fetch`                  | Pull latest changes              |
| `switch -Pbranch=<name>` | Checkout specific branch         |
| `build`                  | Build service (Maven/Gradle)     |
| `start`                  | Start service container          |
| `stop`                   | Stop service container           |
| `restart`                | Restart service container        |
| `logs`                   | Follow service logs              |
| `generateCompose`        | Generate docker-compose fragment |

#### 4.2.4 Frontend Actions

| Action            | Description                        |
|-------------------|------------------------------------|
| `clone`           | Clone all UI repositories          |
| `fetch`           | Pull all UI repositories           |
| `build`           | Build all UI projects              |
| `buildImage`      | Build Node.js builder Docker image |
| `start`           | Start nginx container              |
| `stop`            | Stop nginx container               |
| `logs`            | Follow nginx logs                  |
| `generateCompose` | Generate docker-compose fragment   |

---

## 5. Build Process

### 5.1 Maven Projects (Tomcat Services)

Build environment:
- Docker image: `maven:3-amazoncorretto-<jdk-version>`
- Maven cache: Shared volume at `.build/maven`
- Build command: `mvn install -Dmaven.test.skip=true`

Build steps:
1. Ensure library dependencies are built first
2. Run Maven in Docker container with shared cache
3. Copy WAR artifact to service-specific webapps directory
4. Generate docker-compose fragment

### 5.2 Gradle/Maven Projects (SpringBoot Services)

Build environment:
- Gradle: `gradle:8.5-jdk21`
- Maven: `maven:3-amazoncorretto-21`
- Build command (Gradle): `gradle bootJar -x test`
- Build command (Maven): `mvn package -Dmaven.test.skip=true`

Build steps:
1. Detect build system (Gradle vs Maven)
2. Run build in Docker container
3. Copy JAR artifact to service-specific directory
4. Generate docker-compose fragment

### 5.3 Node.js Projects (Frontend)

Build environment:
- Custom Docker image: `local-node-builder`
- Base: `node:22` with Ruby/Sass for legacy builds
- Node cache: Shared volume at `.build/node`

Build steps:
1. Build Node.js builder Docker image (if not exists)
2. Run project-specific build script in container
3. Copy/merge build artifacts as needed
4. Generate docker-compose fragment for nginx

### 5.4 Build Scripts per Frontend Project

| Project              | Build Script                                             |
|----------------------|----------------------------------------------------------|
| `ui`                 | `./point.sh local && npx bower install && npx grunt ...` |
| `viveka-ui`          | `npm install && npm run build:local`                     |
| `employer-portal-ui` | `npm install && npm run build:spa.local`                 |

---

## 6. Docker Compose Generation

### 6.1 Fragment-Based Architecture

Each service generates its own docker-compose fragment file:

```
.build/compose/
├── 01-db-main.yml
├── 02-db-shared.yml
├── 10-authserver.yml
├── 11-communication.yml
├── 12-lookup.yml
├── 13-s3.yml
├── 14-processor.yml
├── 15-employer-portal.yml
├── 20-remittance-engine.yml
└── 30-frontend.yml
```

### 6.2 File Naming Convention

Files are numbered to ensure correct ordering:
- `01-09`: Database services
- `10-19`: Tomcat services
- `20-29`: SpringBoot services
- `30-39`: Frontend services

### 6.3 Compose Invocation

When starting services, all fragment files are provided to docker-compose:

```bash
docker compose -p localbox \
  -f .build/compose/01-db-main.yml \
  -f .build/compose/02-db-shared.yml \
  -f .build/compose/10-authserver.yml \
  ... \
  up -d [service-names]
```

### 6.4 Required Compose Elements

Each fragment must include:

```yaml
services:
  <service-name>:
    image: <base-image>
    container_name: localbox-<service-name>
    volumes:
      - <app-artifacts>:/path/in/container:ro
      - <config-dir>:/viveka:ro
    environment:
      # Service-specific environment variables
    ports:
      - "<host-port>:<container-port>"
    networks:
      - localbox
    healthcheck:
      test: [...]
      interval: 10s
      timeout: 5s
      retries: 10
      start_period: 60s
    depends_on:
      <dependency>:
        condition: service_healthy
```

### 6.5 Shared Resources

All fragments share:
- Network: `localbox` (bridge driver)
- Volumes: `db-main-data`, `db-shared-data`

---

## 7. Configuration

### 7.1 Default Configuration

| Property              | Default Value                         | Description                 |
|-----------------------|---------------------------------------|-----------------------------|
| `git.baseUrl`         | `git@bitbucket.org:viveka-health-dev` | Git repository base URL     |
| `git.defaultBranch`   | `dev`                                 | Default branch for cloning  |
| `db.main.port`        | `5432`                                | Main database host port     |
| `db.shared.port`      | `5433`                                | Shared database host port   |
| `compose.projectName` | `localbox`                            | Docker Compose project name |

### 7.2 Directory Structure

```
localbox/
├── .build/                    # Build artifacts (gitignored)
│   ├── compose/              # Generated docker-compose fragments
│   ├── maven/                # Maven cache
│   ├── node/                 # Node.js cache
│   ├── projects/             # Cloned repositories
│   ├── webapps/              # WAR files per service
│   │   ├── authserver/
│   │   ├── communication/
│   │   └── ...
│   └── jars/                 # JAR files per service
│       └── remittance-engine/
├── assets/                   # Static configuration
│   ├── nginx/               # Nginx configuration
│   ├── viveka-home/         # Application properties
│   ├── patches/             # Git patches for repos
│   └── Dockerfile-node-builder
├── db/
│   ├── main/
│   └── shared/
├── be/
│   ├── lib/                 # Library projects
│   │   ├── utils/
│   │   ├── security-prototype/
│   │   ├── fs-s3-storage/
│   │   └── vix12parser/
│   ├── tomcat/              # Tomcat services
│   │   ├── authserver/
│   │   ├── communication/
│   │   ├── lookup/
│   │   ├── s3/
│   │   ├── processor/
│   │   └── employer-portal/
│   └── springboot/          # SpringBoot services
│       └── remittance-engine/
└── fe/                      # Frontend
    ├── ui/
    ├── viveka-ui/
    └── employer-portal-ui/
```

### 7.3 Local Overrides

Users can create a `local.properties` file (gitignored) to override defaults:

```properties
# Custom paths
projects.dir=/custom/path/to/projects
build.dir=/custom/path/to/build

# Different git remote
git.baseUrl=git@github.com:your-org

# Different branch
git.defaultBranch=main
```

---

## 8. Environment Requirements

### 8.1 Host Requirements

| Requirement    | Version | Purpose                                        |
|----------------|---------|------------------------------------------------|
| Java           | 21+     | Running build tool (if using Gradle/JVM-based) |
| Docker         | 20.10+  | Container runtime                              |
| Docker Compose | 2.0+    | Service orchestration                          |
| Git            | 2.0+    | Repository management                          |

### 8.2 Recommended Java Installation

```bash
# Using SDKMAN
export JAVA_HOME=/home/<user>/.sdkman/candidates/java/21.0.9-amzn
export PATH=$JAVA_HOME/bin:$PATH
```

### 8.3 Network Requirements

- Ports 80, 5432, 5433, 8081-8090 available on host
- DNS resolution for `*.localtest.me` (resolves to 127.0.0.1)
- Internet access for Docker image pulls

---

## 9. Health Checks

### 9.1 Database Health

```yaml
healthcheck:
  test: ["CMD-SHELL", "pg_isready -U postgres"]
  interval: 5s
  timeout: 5s
  retries: 5
```

### 9.2 Tomcat Service Health

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8080/<context>/health"]
  interval: 10s
  timeout: 5s
  retries: 10
  start_period: 60s
```

### 9.3 SpringBoot Service Health

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8080/actuator/health"]
  interval: 10s
  timeout: 5s
  retries: 10
  start_period: 60s
```

### 9.4 Nginx Health

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:80/health"]
  interval: 10s
  timeout: 5s
  retries: 5
```

---

## 10. Git Operations

### 10.1 Clone with Patches

Some repositories require local patches for development:

1. Clone repository
2. Checkout default branch
3. Apply patches from `assets/patches/<repo-name>/*.patch`

### 10.2 Patch Directory Structure

```
assets/patches/
├── ui/
│   └── LocalBuild-UI.patch
└── employer-portal-ui/
    └── LocalChange-EmpPortalUi.patch
```

---

## 11. Implementation Alternatives

This specification can be implemented using various tools:

### 11.1 Gradle (Reference Implementation)

- Uses Kotlin DSL for build scripts
- Subproject structure mirrors service hierarchy
- Task dependencies handle build/start ordering
- Tab completion via Gradle wrapper

### 11.2 Make

- Makefile with phony targets
- Pattern rules for service operations
- Include files for modular configuration

### 11.3 Custom CLI (Python/Go/Rust)

- Single binary with subcommands
- YAML/TOML configuration files
- Shell completion scripts

### 11.4 Just (Task Runner)

- Justfile with recipes
- Built-in argument handling
- Cross-platform support

### 11.5 Shell Scripts

- Bash scripts with functions
- Sourced configuration files
- Manual completion setup

---

## 12. Success Criteria

1. **Single Command Setup**: New developer can run `clone && buildAll && start`
2. **Independent Services**: Each service can be built/started/stopped individually
3. **Dependency Handling**: Services start in correct order automatically
4. **Fast Iteration**: Rebuilding single service doesn't require full rebuild
5. **Discoverable**: Tab completion shows available commands and services
6. **Configurable**: Local overrides without modifying tracked files
7. **Reproducible**: Same commands produce same results across machines

---

## 13. Service Onboarding Guide

This section describes how to add new services to the localbox environment using convention plugins.

### 13.1 Onboarding a New Tomcat Service

#### 13.1.1 Prerequisites Checklist

| Item                 | Description                                     | Example                           |
|----------------------|-------------------------------------------------|-----------------------------------|
| Service ID           | Unique identifier (lowercase, hyphen-separated) | `claims-processor`                |
| Repository Name      | Git repository name                             | `claims-processor`                |
| JDK Version          | Java version required (8, 11, 17, 21)           | `8`                               |
| WAR Path             | Relative path to WAR artifact after build       | `target/claims-processor-1.0.war` |
| WAR Name             | Renamed artifact in container                   | `claims-processor.war`            |
| Host Port            | Unique port for host binding                    | `8087`                            |
| Health Endpoint      | Health check URL path                           | `/claims-processor/health`        |
| Compose File Number  | Ordering number (10-19 for Tomcat)              | `16`                              |
| Runtime Dependencies | Services required at runtime                    | `db-main`, `authserver`           |
| Build Dependencies   | Library projects for Maven build                | `utils`, `vix12parser`            |

#### 13.1.2 Create Service Configuration

Create `be/tomcat/<service-id>/build.gradle.kts` (just ~15 lines):

```kotlin
plugins {
    id("tomcat-service")
}

tomcatService {
    serviceName = "claims-processor"
    repoName = "claims-processor"
    warSource = "target/claims-processor-1.0.war"
    warName = "claims-processor.war"
    port = 8087
    jdkVersion = 8
    healthEndpoint = "/claims-processor/health"
    composeFileNumber = 16
    buildDependsOn = listOf(":be:lib:utils:build")
}
```

#### 13.1.3 Plugin Configuration Options

| Property               | Required | Default                  | Description                    |
|------------------------|----------|--------------------------|--------------------------------|
| `serviceName`          | Yes      | -                        | Unique service identifier      |
| `repoName`             | No       | serviceName              | Git repository name            |
| `warSource`            | Yes      | -                        | Path to WAR after Maven build  |
| `warName`              | No       | `${serviceName}.war`     | Renamed WAR in container       |
| `port`                 | Yes      | -                        | Host port mapping              |
| `jdkVersion`           | No       | 8                        | JDK version (8, 11, 17, 21)    |
| `healthEndpoint`       | No       | `/${serviceName}/health` | Health check path              |
| `composeFileNumber`    | No       | 10                       | Ordering number (10-19)        |
| `buildDependsOn`       | No       | empty                    | Library build dependencies     |
| `hasOwnRepo`           | No       | true                     | Set false if uses another repo |
| `environmentVariables` | No       | standard                 | Custom env vars map            |

#### 13.1.4 Register the Service

1. **Add to `settings.gradle.kts`:**
```kotlin
include("be:tomcat:<service-id>")
```

2. **Add runtime dependencies to root `build.gradle.kts`:**
```kotlin
val serviceDependencies = mapOf(
    // ... existing ...
    "<service-id>" to listOf("db-main", "authserver"),
)
```

3. **Add to `be/tomcat/build.gradle.kts` aggregate tasks**

4. **Optionally create `assets/viveka-home/<service-id>.properties`**

#### 13.1.5 What the Plugin Provides Automatically

The `tomcat-service` plugin generates these tasks:
- `clone`, `fetch`, `switch` - Git operations
- `build` - Maven build in Docker
- `buildImage` - Creates Docker image with WAR + config baked in
- `generateCompose` - Creates docker-compose fragment
- `start`, `stop`, `restart`, `logs` - Container lifecycle

**Docker Image Contents:**
- Base: `tomcat:9.0-jdk<version>`
- WAR deployed to `/usr/local/tomcat/webapps/`
- Config copied to `/viveka` (no volume mount needed)

---

### 13.2 Onboarding a New SpringBoot Service

#### 13.2.1 Prerequisites Checklist

| Item                 | Description             | Example                 |
|----------------------|-------------------------|-------------------------|
| Service ID           | Unique identifier       | `eligibility-engine`    |
| Repository Name      | Git repository name     | `eligibility-engine`    |
| Build System         | Gradle or Maven         | `gradle`                |
| JDK Version          | Java version (17 or 21) | `21`                    |
| Host Port            | Unique port (8091+)     | `8091`                  |
| Compose File Number  | Ordering (20-29)        | `21`                    |
| Runtime Dependencies | Required services       | `db-main`, `authserver` |

#### 13.2.2 Create Service Configuration

Create `be/springboot/<service-id>/build.gradle.kts` (~15 lines):

```kotlin
plugins {
    id("springboot-service")
}

springBootService {
    serviceName = "eligibility-engine"
    repoName = "eligibility-engine"
    jarName = "app.jar"
    port = 8091
    jdkVersion = 21
    buildSystem = "gradle"  // or "maven"
    springProfile = "local"
    composeFileNumber = 21
}
```

#### 13.2.3 Plugin Configuration Options

| Property               | Required | Default            | Description               |
|------------------------|----------|--------------------|---------------------------|
| `serviceName`          | Yes      | -                  | Unique service identifier |
| `repoName`             | No       | serviceName        | Git repository name       |
| `jarName`              | No       | `app.jar`          | JAR filename in image     |
| `port`                 | Yes      | -                  | Host port mapping         |
| `jdkVersion`           | No       | 21                 | JDK version (17, 21)      |
| `buildSystem`          | No       | `gradle`           | `gradle` or `maven`       |
| `springProfile`        | No       | `local`            | Active Spring profile     |
| `healthEndpoint`       | No       | `/actuator/health` | Health check path         |
| `composeFileNumber`    | No       | 20                 | Ordering (20-29)          |
| `environmentVariables` | No       | standard           | Custom env vars           |

#### 13.2.4 Register the Service

1. **Add to `settings.gradle.kts`**
2. **Add runtime dependencies to root `build.gradle.kts`**
3. **Add to `be/springboot/build.gradle.kts` aggregate tasks**

#### 13.2.5 What the Plugin Provides

The `springboot-service` plugin generates:
- `clone`, `fetch`, `switch` - Git operations
- `build` - Gradle/Maven build in Docker
- `buildImage` - Docker image with JAR + config baked in
- `generateCompose` - Creates docker-compose fragment
- `start`, `stop`, `restart`, `logs` - Container lifecycle

**Docker Image Contents:**
- Base: `amazoncorretto:<jdkVersion>`
- JAR at `/app/app.jar`
- Config at `/viveka`
- Entrypoint: `java -jar /app/app.jar`

---

### 13.3 Onboarding a New Frontend Module

#### 13.3.1 Prerequisites

| Item             | Description       | Example         |
|------------------|-------------------|-----------------|
| Module ID        | Unique identifier | `admin-ui`      |
| Repository Name  | Git repository    | `admin-ui`      |
| Build Command    | npm/yarn build    | `npm run build` |
| Output Directory | Built files       | `dist`          |

#### 13.3.2 Create Module Configuration

Create `fe/<module-id>/build.gradle.kts`:

```kotlin
plugins {
    id("frontend-module")
}

frontendModule {
    moduleName = "admin-ui"
    repoName = "admin-ui"
    buildCommand = "npm install && npm run build"
    outputDir = "dist"
    requiresPatches = false
}
```

#### 13.3.3 Register the Module

1. **Add to `settings.gradle.kts`:**
```kotlin
include("fe:<module-id>")
```

2. **Add to `fe/build.gradle.kts` aggregate tasks**

3. **Update nginx config to serve the module**

4. **Update `fe/build.gradle.kts` generateCompose to mount output**

---

### 13.4 Onboarding Checklist Summary

#### New Tomcat Service
- [ ] Create `be/tomcat/<id>/build.gradle.kts` with `tomcat-service` plugin
- [ ] Add to `settings.gradle.kts`
- [ ] Add to `serviceDependencies` map
- [ ] Add to aggregate tasks
- [ ] Assign unique port (8087+) and compose number (16-19)

#### New SpringBoot Service
- [ ] Create `be/springboot/<id>/build.gradle.kts` with `springboot-service` plugin
- [ ] Add to `settings.gradle.kts`
- [ ] Add to `serviceDependencies` map
- [ ] Add to aggregate tasks
- [ ] Assign unique port (8091+) and compose number (21-29)

#### New Frontend Module
- [ ] Create `fe/<id>/build.gradle.kts` with `frontend-module` plugin
- [ ] Add to `settings.gradle.kts`
- [ ] Add to aggregate tasks
- [ ] Update nginx configuration

---

## Appendix A: Port Mapping


| Port | Service                |
|------|------------------------|
| 80   | nginx (HTTP)           |
| 5432 | db-main (PostgreSQL)   |
| 5433 | db-shared (PostgreSQL) |
| 8081 | authserver             |
| 8082 | communication          |
| 8083 | lookup                 |
| 8084 | s3                     |
| 8085 | processor              |
| 8086 | employer-portal        |
| 8090 | remittance-engine      |
| 9001 | nginx (additional)     |
| 9002 | nginx (additional)     |

---

## Appendix B: Environment Variables

### Database Connection

| Variable               | Description          |
|------------------------|----------------------|
| `LOCAL_POSTGRES_USER`  | Main DB username     |
| `LOCAL_POSTGRES_PASS`  | Main DB password     |
| `LOCAL_POSTGRES_NAME`  | Main DB name         |
| `LOCAL_POSTGRES_HOST`  | Main DB bind address |
| `LOCAL_POSTGRES_PORT`  | Main DB port         |
| `SHARED_POSTGRES_USER` | Shared DB username   |
| `SHARED_POSTGRES_PASS` | Shared DB password   |
| `SHARED_POSTGRES_NAME` | Shared DB name       |

### Service Discovery (Container Environment)

| Variable               | Description                    |
|------------------------|--------------------------------|
| `POSTGRES_HOST`        | Main database hostname         |
| `POSTGRES_PORT`        | Main database port             |
| `SHARED_POSTGRES_HOST` | Shared database hostname       |
| `SHARED_POSTGRES_PORT` | Shared database port           |
| `AUTHSERVER_HOST`      | Auth server hostname           |
| `AUTHSERVER_PORT`      | Auth server port               |
| `COMMUNICATION_HOST`   | Communication service hostname |
| `VIVEKA_HOME`          | Application config directory   |

---

## Appendix C: Glossary

| Term                  | Definition                                                      |
|-----------------------|-----------------------------------------------------------------|
| **Fragment**          | Individual docker-compose YAML file for one service             |
| **Library Project**   | Maven project that produces JARs used by other services         |
| **Service**           | Runnable Docker container (database, Tomcat, SpringBoot, nginx) |
| **Webapps Directory** | Directory containing WAR files mounted into Tomcat              |
| **VIVEKA_HOME**       | Directory containing application property files                 |
