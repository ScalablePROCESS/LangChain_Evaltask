# Déploiement sur un VPS KVM LWS

Cette configuration déploie le serveur FastAPI avec Docker Compose :

- **Caddy** : terminaison TLS automatique Let's Encrypt et reverse proxy ;
- **application** : FastAPI/Gunicorn, non exposée directement sur Internet ;
- **Redis** : réseau interne uniquement, authentifié et persistant ;
- **ChromaDB** : volume Docker persistant ;
- **knowledge** : connaissances du dépôt montées en lecture seule dans le conteneur.

## Pré-requis LWS

- VPS KVM sous Debian 12 ou Ubuntu 24.04 ;
- DNS `A/AAAA` de `DOMAIN` pointant vers l'IP du VPS ;
- ports entrants `80/tcp`, `443/tcp` et `22/tcp` autorisés ;
- Docker Engine et Docker Compose v2 installés.

Ne pas ouvrir `6379` ni `8000` dans le firewall LWS ou `ufw`.

## Première installation

```bash
sudo mkdir -p /opt/langchain-evaltask
sudo chown "$USER":"$USER" /opt/langchain-evaltask
cd /opt/langchain-evaltask
git clone <URL_DU_DEPOT> .

cp deploy/.env.prod.example deploy/.env
chmod 600 deploy/.env
sed -i 's/langchain.example.com/api.example.com/' deploy/.env
sed -i 's/admin@example.com/ops@example.com/' deploy/.env
openssl rand -hex 32  # copier une valeur dans JWT_SECRET
openssl rand -hex 32  # copier une autre valeur dans REDIS_PASSWORD

# Vérifier la configuration sans démarrer les services
docker compose --env-file deploy/.env -f deploy/docker-compose.prod.yml config

# Construire et démarrer
docker compose --env-file deploy/.env -f deploy/docker-compose.prod.yml up -d --build
```

> Le secret `JWT_SECRET` doit être identique à celui utilisé par les plateformes EvalTask clientes. Ne réutilisez pas `REDIS_PASSWORD`.

## Vérification

```bash
docker compose --env-file deploy/.env -f deploy/docker-compose.prod.yml ps
curl --fail https://api.example.com/api/v1/health
curl --fail https://api.example.com/api/v1/ready
```

Les endpoints `/docs`, `/redoc`, `/openapi.json`, `/metrics` et les endpoints de diagnostic Redis/circuit breaker sont bloqués par Caddy dans cette configuration. Les healthchecks restent publics afin de permettre la supervision. Si l'API est destinée à un usage strictement backend, ajoutez aussi une restriction réseau/WAF sur le domaine.

## Mises à jour

```bash
cd /opt/langchain-evaltask
git pull --ff-only
docker compose --env-file deploy/.env -f deploy/docker-compose.prod.yml build --pull
docker compose --env-file deploy/.env -f deploy/docker-compose.prod.yml up -d
docker compose --env-file deploy/.env -f deploy/docker-compose.prod.yml ps
```

## Logs et rollback

```bash
docker compose --env-file deploy/.env -f deploy/docker-compose.prod.yml logs -f --tail=200 app
docker compose --env-file deploy/.env -f deploy/docker-compose.prod.yml logs -f caddy
```

Avant une mise à jour, conserver le commit actuellement déployé et une sauvegarde des volumes `chromadb_data` et `redis_data`. Les connaissances sont versionnées dans le dépôt et montées en lecture seule. Pour revenir en arrière, restaurer le commit précédent puis reconstruire l'image ; ne pas supprimer les volumes.

## Sauvegarde minimale

Les données ChromaDB et Redis sont locales au VPS : mettre en place une sauvegarde chiffrée externe, au minimum quotidienne, et tester la restauration. Une panne du VPS sans sauvegarde entraîne une perte de la mémoire Redis et du vectorstore local.

## Firewall conseillé

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

Adapter la règle SSH à une IP d'administration fixe si possible.
