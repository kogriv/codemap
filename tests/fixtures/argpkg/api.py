"""The function whose signature a refactorer wants to change."""


def configure(name, *, mode="fast", retries=0):
    return (name, mode, retries)
