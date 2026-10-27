# omarchy-k8s-platform

GitOps source of truth for a multi-environment Kubernetes lab. A single hub
Argo CD deploys every app to the dev, staging and prod worker clusters, so all
environments show up in one Argo CD view.

```
hub cluster (mgmt): Argo CD
  root                              app of apps -> bootstrap/
   ├─ AppProjects platform, default (locked down)
   └─ ApplicationSet environments   one app per registered worker cluster
        ├─ env-dev      -> environments/dev/
        │    └─ ApplicationSet hello-world-dev -> hello-world-<app>-dev  ──> dev cluster
        ├─ env-staging  -> environments/staging/                         ──> staging cluster
        └─ env-prod     -> environments/prod/                            ──> prod cluster
```

## Layout

| Path | What lives there |
|---|---|
| `bootstrap/` | Hub plumbing the root app syncs: the `platform` project and the `environments` ApplicationSet |
| `environments/<env>/<group>/` | Per environment and app group: an AppProject and an ApplicationSet targeting that env's cluster |
| `apps/<group>/<app>/` | Source, Dockerfile, `values.yaml` (base) and optional `values-<env>.yaml` overrides |
| `charts/web-service/` | Reusable, hardened Helm chart every app is deployed with |

An environment is enabled by registering its cluster in Argo CD with an
`environment=<name>` label. Unregistered environments get no apps.

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

## Endpoints

| | dev | staging | prod |
|---|---|---|---|
| Python | :30001 | :30101 | :30201 |
| .NET | :30002 | :30102 | :30202 |
| Node | :30003 | :30103 | :30203 |
| Java | :30004 | :30104 | :30204 |

Argo CD (all environments): http://localhost:30080

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
