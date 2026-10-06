# Contributing to SSHelf

Thanks for improving SSHelf. This project lives at **[github.com/georgegozal/sshelf](https://github.com/georgegozal/sshelf)** — that repository is the upstream; forks and pull requests should target it.

## Before you start

- **Bug fixes and small improvements** — a pull request is enough; mention what you tested.
- **Large features** (new UI toolkit, new protocols, storage changes) — open an [issue](https://github.com/georgegozal/sshelf/issues) first so we can agree on direction and avoid duplicate work.
- **Security** — if you find a vulnerability, please do not open a public issue with exploit details; contact the maintainer privately.

## Development setup

See [docs/development.md](docs/development.md) for venv, running the PyQt app, and project layout.

The default GUI is **PyQt6** (`python main.py` or `sshelf gui`). An experimental **GTK4** build lives under `src/gtkui/`; see the [GTK4 section in README.md](README.md#gtk4-build-experimental) for system packages and `sshelf gui --gtk`.

## How to contribute (fork + pull request)

1. **Fork** [georgegozal/sshelf](https://github.com/georgegozal/sshelf) on GitHub (or ensure your fork’s default branch is up to date with upstream `main`).
2. **Clone your fork** and add upstream:
   ```bash
   git remote add upstream git@github.com:georgegozal/sshelf.git
   git fetch upstream
   git checkout main
   git merge upstream/main
   ```
3. **Create a branch** with a short descriptive name, e.g. `fix/hostkey-prompt` or `feat/gtk-preferences`.
4. **Make your changes** — keep diffs focused; match existing style in the files you touch.
5. **Test** what you changed (PyQt session, CLI, or GTK if you touched `src/gtkui/` or shared protocol code).
6. **Commit** with clear messages (see below).
7. **Push** to your fork and open a **pull request** against `georgegozal/sshelf` **`main`**.
8. Describe **what** changed and **how you tested it** in the PR body.

Maintainers review PRs on GitHub; you do not need direct write access to the upstream repo.

### Splitting large work

If a change touches several areas (for example, a security fix plus a new UI port), consider **multiple PRs** so critical fixes can merge quickly. Security-related changes (SSH, keychain, host keys) deserve their own review either way.

## Commit messages

Use the style already in the log:

- `fix: …` — bug or security fix  
- `feat: …` — new behavior  
- `refactor: …` — internal restructuring without user-visible change  
- `docs: …` — documentation only  

Keep the subject line imperative and under ~72 characters; add a body if the why is not obvious.

## Code guidelines

- **Shared logic** — put toolkit-neutral code in `src/protocols/`, `src/models/`, or `src/storage/`; keep Qt in `src/ui/` and GTK in `src/gtkui/`.
- **Dependencies** — PyQt and pip packages go in `requirements.txt`; GTK/VTE stays documented as system packages (see README).
- **Scope** — avoid unrelated formatting or drive-by refactors in the same PR as a feature fix.

## License

By contributing, you agree that your contributions are licensed under the same terms as the project: **AGPL-3.0** (see [LICENSE](LICENSE)).
