import dotenv
import logfire

dotenv.load_dotenv()

# Trace agent + judge runs (token usage/cost) with Logfire. Matches the rest of
# the project; without a token configured this is a no-op.
logfire.configure(send_to_logfire="if-token-present", console=False)
logfire.instrument_pydantic_ai()