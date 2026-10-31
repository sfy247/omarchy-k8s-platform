# omarchy-k8s-platform

GitOps source of truth for a multi-environment Kubernetes lab. A single hub
Argo CD deploys every app to the dev, staging and prod worker clusters, so all
environments show up in one Argo CD view.

```
hub cluster (mgmt): Argo CD
  root                              app of apps -> bootstrap/
   ├─ AppProjects platform, default (locked down), cluster-addons
   ├─ ApplicationSets cert-manager, envoy-gateway, gateway   on every cluster (hub + workers)
   └─ ApplicationSet environments   one app per registered worker cluster
        ├─ env-dev      -> environments/dev/
        │    └─ ApplicationSet hello-world-dev -> hello-world-<app>-dev  ──> dev cluster
        ├─ env-staging  -> environments/staging/                         ──> staging cluster
        └─ env-prod     -> environments/prod/                            ──> prod cluster
```

## Layout

| Path | What lives there |
|---|---|
| `bootstrap/` | Hub plumbing the root app syncs: projects, the `environments` and `hub` ApplicationSets, and `cluster-addons.yaml` (add-on versions pinned there) |
| `hub/` | Services that run only on the hub: the developer portal (`developer-portal/`) and Argo CD Image Updater (`image-updater/`) |
| `catalog/` | What the portal's **Discover** section shows: the lab domain, systems, clusters, Argo CD, gateway, Postgres |
| `charts/developer-portal/` | Official Backstage chart plus its own CloudNativePG database, HTTPRoute and NetworkPolicies |
| `cluster-addons/gateway/` | Per-cluster HTTPS entry point: Envoy Gateway, wildcard certificate, HTTP→HTTPS redirect |
| `environments/<env>/<group>/` | Per environment and app group: an AppProject and an ApplicationSet targeting that env's cluster |
| `apps/<group>/<app>/` | Source, Dockerfile, `values.yaml` (base), optional `values-<env>.yaml` overrides, and `catalog-info.yaml` (its entry in Discover) |
| `charts/web-service/` | Reusable, hardened Helm chart every app is deployed with |

An environment is enabled by registering its cluster in Argo CD with an
`environment=<name>` label. Unregistered environments get no apps.

## DNS and TLS

Each app is served at `https://<app>.<env>.<domain>`, and Argo CD at
`https://argocd.<domain>`. **This repo contains no domain, hostname or port.**
The provisioning tooling writes them as annotations on each cluster's Argo CD
registration, and the ApplicationSets read them from there:

| Annotation | Example | Used for |
|---|---|---|
| `lab/domain` | `dev.<domain>` | App hostnames (`<app>.<lab/domain>`) |
| `lab/gateway-hostname` | `*.dev.<domain>` | Gateway listener and certificate |
| `lab/gateway-http-nodeport`, `lab/gateway-https-nodeport` | `31080`, `31443` | Envoy NodePorts |
| `lab/argocd-route` | `true` on the hub | Route Argo CD through the gateway |

Certificates come from cert-manager, issued by a local CA. The CA's key is put
into each cluster by the provisioning tooling and never stored in Git.

## Developer portal

Backstage runs on the hub at `https://backstage.<domain>`. Its code and
templates live in [omarchy-k8s-portal](https://github.com/sfy247/omarchy-k8s-portal);
this repo only deploys it. Templates open pull requests here that add
`apps/services/<name>/` and an `ImageUpdater` rule in
`environments/dev/services/image-updates/`.

**Image roll-forward:** Argo CD Image Updater watches GHCR. When a newer
`sha-<commit>` image appears, it commits the tag to the app's values file
(the portal's own `charts/developer-portal/values.yaml`, or a service's
`values-dev.yaml`) and Argo CD deploys it. Commits from
`argocd-image-updater` in this repo's history are those roll-forwards.

## Security defaults

- **Projects:** Argo CD's built-in `default` project is emptied, so every app
  must use a scoped project. `platform` can only create AppProjects and
  ApplicationSets. Each `<group>-<env>` project allows one repo, one namespace
  on one cluster, and only Deployment / Service / ServiceAccount / NetworkPolicy.
- **Namespaces:** created by Argo CD with Pod Security Admission `restricted`.
- **Pods:** non-root (UID 10001), read-only root filesystem, all capabilities
  dropped, no privilege escalation, `RuntimeDefault` seccomp, no
  service-account token. The .NET image is chiseled (no shell).
- **Network:** one NetworkPolicy per app, allowing HTTP in and DNS out only.
- **TLS:** HTTPS everywhere; plain HTTP only redirects. The lab CA is
  name-constrained to the lab domain, so trusting it can't expose other sites.
- **Add-ons:** the `cluster-addons` project can create cluster-scoped kinds
  (CRDs, webhooks), but only into its own namespaces.

## Endpoints

| | dev | staging | prod |
|---|---|---|---|
| Python | `https://python.dev.<domain>` | `https://python.staging.<domain>` | `https://python.prod.<domain>` |
| .NET | `https://dotnet.dev.<domain>` | … | … |
| Node | `https://node.dev.<domain>` | … | … |
| Java | `https://java.dev.<domain>` | … | … |

Argo CD (all environments): `https://argocd.<domain>`. Raw NodePorts are also
published on 127.0.0.1 for debugging: dev 30001+, staging 30101+, prod 30201+,
and Argo CD on 30080.

## Common changes

**Add an app to a group:** create `apps/<group>/<app>/` with a `Dockerfile` and
`values.yaml`. Set `nameOverride`, `image.repository` (`<group>-<app>`),
`image.tag`, and a free `service.nodePort` in 30001-30010. Push it, then run
`make images` in omarchy-k8s-ansible. Every environment's ApplicationSet picks
it up.

**Override per environment:** add `apps/<group>/<app>/values-<env>.yaml`. For
example, prod runs 2 replicas via `values-prod.yaml`.

**Add an app group:** create `apps/<group>/`, then copy
`environments/<env>/hello-world/` to `environments/<env>/<group>/` for each
environment. Replace `hello-world` with the group name in both files.

**Add an environment:** copy an `environments/<env>/` folder, then add the
environment to `lab_environments` in omarchy-k8s-ansible.

## Provisioning

Clusters, Argo CD, cluster registration and the root app are provisioned by
[omarchy-k8s-ansible](https://github.com/sfy247/omarchy-k8s-ansible):

```bash
cd ../omarchy-k8s-ansible && make deploy
```
