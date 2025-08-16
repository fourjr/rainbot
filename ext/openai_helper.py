import openai


def run_openai_moderation(content):
    return openai.Moderation.create(input=content)
