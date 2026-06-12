import asyncio

import logfire

from src.agent.agent import SQLAgentConfig, create_agent, run_agent_stream
from src.agent.llm import LLMProvider
from src.agent.models import RAGResponse
from src.agent.tools import SQLTools


def main():
    agent = create_agent(SQLAgentConfig(), SQLTools(), LLMProvider())
    message_history = []
    prompt_label = "You (write 'stop' to stop): "

    with logfire.span('user_session'):
        while True:
            prompt = input(prompt_label)
            if not prompt or prompt.lower().strip() == "stop":
                break

            agent_run = asyncio.run(
                run_agent_stream(agent, prompt, message_history=message_history)
            )
            if not agent_run:
                continue

            message_history = agent_run.all_messages()
            output = agent_run.output
            print()

            if isinstance(output, str):
                # Plain-text clarification from the agent — prompt user for answer
                print(f"Agent: {output}")
                prompt_label = "Your answer (write 'stop' to stop): "
            else:
                # Final structured RAGResponse — reset to normal prompt
                prompt_label = "You (write 'stop' to stop): "


if __name__ == "__main__":
    main()
