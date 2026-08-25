# Getting help

**A skill gives wrong or outdated guidance, or fails to load.**
Open a [skill bug](https://github.com/Aarvion-AI/stackwise-skills/issues/new?template=skill-fix.yml).
Include the file and line so the fix is a one-line PR.

**You want to add a framework.**
Claim it with a [new skill issue](https://github.com/Aarvion-AI/stackwise-skills/issues/new?template=new-skill.yml),
then follow [CONTRIBUTING.md](CONTRIBUTING.md).

**You have a question, or an idea you want to sanity-check first.**
Use [Discussions](https://github.com/Aarvion-AI/stackwise-skills/discussions).
Half-formed ideas are welcome there; issues are for work that is ready to be done.

**Something looks like a security problem.**
Follow [SECURITY.md](SECURITY.md) and report it privately, not in a public issue.

**The plugin will not install.**
Check that `/plugin marketplace add Aarvion-AI/stackwise-skills` succeeded before
`/plugin install stackwise@stackwise-skills`, and that you are on a current
Claude Code. If it still fails, open an issue with your Claude Code version and
the exact error.
