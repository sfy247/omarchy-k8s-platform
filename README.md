# omarchy-k8s-platform

GitOps source of truth for a local Kubernetes lab: hello-world services in
Python, C#/.NET, Node and Java, deployed to a local [kind](https://kind.sigs.k8s.io) cluster by Argo CD using the app-of-apps pattern.

```
root Application                 (applied by omarchy-k8s-ansible)
  └─ argocd/                     root app syncs this folder
       ├─ namespaces/            hello-apps ns, Pod Security "restricted"
       ├─ projects/              AppProject "hello" (least privilege)
       └─ applicationsets/       ApplicationSet: one app per apps/<name>/
            ├─ hello-python  ─┐
            ├─ hello-dotnet   ├─ charts/hello-app + apps/<name>/values.yaml
            ├─ hello-node     │
            └─ hello-java    ─┘
```

## Security defaults

- Images run as UID 10001; .NET uses a chiseled (shell-less) base
- Pods: `runAsNonRoot`, read-only root filesystem, all capabilities dropped,
  no privilege escalation, `RuntimeDefault` seccomp, no service-account token
- Namespace enforces Pod Security Admission `restricted`
- NetworkPolicy per app: HTTP in, DNS out only
- AppProject allows one repo, one namespace, and only Deployment / Service /
  ServiceAccount / NetworkPolicy; no cluster-scoped resources

## Usage

The cluster, Argo CD and this repo's bootstrap are provisioned by
[omarchy-k8s-ansible](https://github.com/sfy247/omarchy-k8s-ansible):

```bash
cd ../omarchy-k8s-ansible && make deploy K=1
```

After that, Argo CD deploys whatever is pushed to `main` here.

| Service   | URL                     |
|-----------|-------------------------|
| Argo CD   | http://localhost:30080  |
| Python    | http://localhost:30001  |
| .NET      | http://localhost:30002  |
| Node      | http://localhost:30003  |
| Java      | http://localhost:30004  |

To add a service, create `apps/<name>/` with a `Dockerfile` and `values.yaml`
(pick a free `service.nodePort` in 30001-30010), push, and run `make deploy` in omarchy-k8s-ansible to build its image. The
ApplicationSet and the playbook both discover it automatically.

Rebuild from scratch any time with `make redeploy` (in omarchy-k8s-ansible).
