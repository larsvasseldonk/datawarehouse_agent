from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from openai import AsyncOpenAI

import os


class LLMProvider:
    """
    Provides methods to create and configure language models for the agent.
    """

    def __init__(self, model_name: str = "gpt-4.1-mini"):
        self.model_name = model_name

    def get_chatns_model(self):
        """
        Creates and returns an OpenAIChatModel configured to use the ChatNS API.
        """
        api_key = os.getenv("CHATNS_API_KEY")
        if not api_key:
            raise ValueError(
                "Missing CHATNS_API_KEY in environment. Add it to your .env file."
            )

        chatns_base_url = "https://gateway.apiportal.ns.nl/genai/v1"
        # Let op: de AsyncOpenAI-client vereist altijd een `api_key`-parameter en
        # valt anders terug op de `OPENAI_API_KEY` omgevingsvariabele. Voor ChatNS
        # verloopt authenticatie uitsluitend via een custom request header, de `api_key`
        # wordt niet verstuurd. Daarom `api_key="not-used"` als placeholder om deze
        # validatie te omzeilen.
        model = OpenAIChatModel(
            self.model_name,
            provider=OpenAIProvider(
                openai_client=AsyncOpenAI(
                    api_key="not-used",
                    base_url=chatns_base_url,
                    default_headers={"Ocp-Apim-Subscription-Key": api_key},
                ),
            ),
        )

        return model

    def get_openai_model(self):
        """
        Creates and returns an OpenAIChatModel configured to use the OpenAI API.
        """
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "Missing OPENAI_API_KEY in environment. Add it to your .env file."
            )

        model = OpenAIChatModel(
            self.model_name,
            provider=OpenAIProvider(
                openai_client=AsyncOpenAI(
                    base_url="https://api.openai.com/v1",
                    default_headers={"Authorization": f"Bearer {api_key}"},
                ),
            ),
        )
        return model
