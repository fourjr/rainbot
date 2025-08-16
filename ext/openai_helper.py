import openai


def run_openai_moderation(content, api_key):
    openai.api_key = api_key
    return openai.Moderation.create(input=content)
