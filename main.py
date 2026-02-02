"""CLI entry point for the Transaction Dispute Resolution Agent."""

import argparse
import sys
from pathlib import Path

from src.config import settings
from src.data.seed import seed_data, reset_data
from src.data.storage import Storage
from src.utils.session import set_current_user_id


def ensure_data_exists():
    """Ensure mock data files exist, seeding if necessary."""
    storage = Storage()
    transactions = storage.get_transactions()
    merchants = storage.get_merchants()

    if not transactions or not merchants:
        print("Initializing mock data...")
        seed_data()
        print()


def run_repl(user_id: str, provider: str | None = None):
    """Run the interactive REPL."""
    # Import here to avoid loading LLM until needed
    from src.agent.core import DisputeAgent

    # Set the current user in session context
    set_current_user_id(user_id)

    print("=" * 60)
    print("Transaction Dispute Resolution Agent")
    print("=" * 60)
    print(f"User: {user_id}")
    print(f"Provider: {provider or settings.llm_provider}")
    print()
    print("Commands:")
    print("  /help     - Show available commands")
    print("  /clear    - Clear conversation history")
    print("  /history  - Show conversation history")
    print("  /disputes - List your disputes")
    print("  /quit     - Exit the agent")
    print()
    print("Type your question about a transaction to get started.")
    print("-" * 60)

    try:
        agent = DisputeAgent(user_id=user_id, provider=provider)
    except ValueError as e:
        print(f"\nError: {e}")
        print("\nTo fix this, create a .env file with your API key:")
        print("  For Gemini: GEMINI_API_KEY=your_api_key_here")
        print("  For Groq:   GROQ_API_KEY=your_api_key_here")
        print("\nGet API keys at:")
        print("  Gemini: https://makersuite.google.com/app/apikey")
        print("  Groq:   https://console.groq.com/keys")
        sys.exit(1)

    while True:
        try:
            user_input = input("\nYou: ").strip()

            if not user_input:
                continue

            # Handle commands
            if user_input.startswith("/"):
                command = user_input.lower()

                if command == "/quit" or command == "/exit":
                    print("\nGoodbye!")
                    break

                elif command == "/help":
                    print("\nAvailable commands:")
                    print("  /help     - Show this help message")
                    print("  /clear    - Clear conversation history")
                    print("  /history  - Show conversation history")
                    print("  /disputes - List your disputes")
                    print("  /quit     - Exit the agent")
                    print("\nExample queries:")
                    print('  "I don\'t recognize this $50 charge from Coffee Palace"')
                    print('  "Why was I charged $15 yesterday?"')
                    print('  "What\'s this Amazon charge for?"')
                    print('  "I want to dispute transaction txn_001"')
                    continue

                elif command == "/clear":
                    agent.clear_history()
                    print("\nConversation history cleared.")
                    continue

                elif command == "/history":
                    history = agent.get_history()
                    if not history:
                        print("\nNo conversation history.")
                    else:
                        print("\nConversation history:")
                        print("-" * 40)
                        for msg in history:
                            role = "You" if msg["role"] == "user" else "Agent"
                            content = msg["content"]
                            if len(content) > 200:
                                content = content[:200] + "..."
                            print(f"\n{role}: {content}")
                    continue

                elif command == "/disputes":
                    from src.tools.disputes import list_user_disputes
                    result = list_user_disputes.invoke({})
                    if result["count"] == 0:
                        print("\nYou have no disputes on file.")
                    else:
                        print(f"\nYou have {result['count']} dispute(s):")
                        for d in result["disputes"]:
                            print(f"  - {d['id'][:8]}... | {d['status']} | {d['amount']} at {d['merchant']}")
                    continue

                else:
                    print(f"\nUnknown command: {user_input}")
                    print("Type /help for available commands.")
                    continue

            # Process with agent
            print("\nAgent: ", end="", flush=True)
            response = agent.process_message(user_input)
            print(response)

        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except EOFError:
            print("\n\nGoodbye!")
            break


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Transaction Dispute Resolution Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                      # Start with default user and provider
  python main.py --user user_002      # Start with specific user
  python main.py --provider groq      # Use Groq instead of Gemini
  python main.py --reset              # Reset mock data to defaults
  python main.py --seed               # Seed data without running agent
        """,
    )

    parser.add_argument(
        "--user",
        type=str,
        default=settings.default_user_id,
        help=f"User ID for the session (default: {settings.default_user_id})",
    )

    parser.add_argument(
        "--provider",
        type=str,
        choices=["gemini", "groq"],
        default=None,
        help=f"LLM provider to use (default: {settings.llm_provider})",
    )

    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset all data to defaults (clears sessions, disputes, preferences)",
    )

    parser.add_argument(
        "--seed",
        action="store_true",
        help="Seed mock data and exit",
    )

    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Custom data directory path",
    )

    args = parser.parse_args()

    # Handle data directory override
    if args.data_dir:
        settings.data_dir = args.data_dir

    # Handle reset
    if args.reset:
        print("Resetting all data to defaults...")
        reset_data(args.data_dir)
        print("Done!")
        return

    # Handle seed-only
    if args.seed:
        print("Seeding mock data...")
        seed_data(args.data_dir)
        print("Done!")
        return

    # Ensure data exists
    ensure_data_exists()

    # Run the REPL
    run_repl(args.user, args.provider)


if __name__ == "__main__":
    main()
