#!/usr/bin/env python3
"""Script to view all shift changes in the database."""

import asyncio
from sqlmodel import Session, select
from sqlalchemy.exc import SQLAlchemyError
from rich.console import Console
from rich.table import Table
from rich.pretty import pprint

# Adjust the import path based on your project structure
# This assumes your script is in the 'scripts' directory and your models/db are accessible
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.session import get_session, engine # Assuming get_session is a regular function now
from models.shift_change import ShiftChange

console = Console()

def format_optional(value):
    return str(value) if value is not None else "-"

async def view_all_shift_changes():
    """Connects to the database and prints all shift changes."""
    console.print("[bold cyan]Attempting to fetch all shift changes...[/bold cyan]")

    try:
        # The get_session() in your project seems to be a dependency for FastAPI
        # and might not work directly as an async context manager here.
        # We'll use the engine to create a session directly for this script.
        with Session(engine) as session:
            statement = select(ShiftChange).order_by(ShiftChange.created_at.desc())
            shift_changes = session.exec(statement).all()

            if not shift_changes:
                console.print("[yellow]No shift changes found in the database.[/yellow]")
                return

            table = Table(title="[bold green]All Shift Changes[/bold green]", show_lines=True)

            # Define columns
            columns = [
                "ID", "Employee ID", "Created By ID", "Change Type", 
                "Effective Date", "Reason", "Notes", 
                "Orig Start", "Orig End", "Orig Dealership",
                "New Start", "New End", "New Dealership",
                "Swap Employee ID", "Created At", "Status", 
                "Notified", "Viewed At"
            ]
            for col in columns:
                table.add_column(col, overflow="fold")

            # Add rows
            for sc in shift_changes:
                table.add_row(
                    str(sc.id),
                    format_optional(sc.employee_id),
                    format_optional(sc.created_by_owner_id),
                    format_optional(sc.change_type.value if sc.change_type else None), # Assuming change_type is an Enum
                    format_optional(sc.effective_date),
                    format_optional(sc.reason),
                    format_optional(sc.notes),
                    format_optional(sc.original_start_time),
                    format_optional(sc.original_end_time),
                    format_optional(sc.original_dealership_id),
                    format_optional(sc.new_start_time),
                    format_optional(sc.new_end_time),
                    format_optional(sc.new_dealership_id),
                    format_optional(sc.swap_with_employee_id),
                    format_optional(sc.created_at.strftime("%Y-%m-%d %H:%M:%S") if sc.created_at else None),
                    format_optional(sc.status),
                    format_optional(sc.employee_notified),
                    format_optional(sc.employee_viewed_at.strftime("%Y-%m-%d %H:%M:%S") if sc.employee_viewed_at else None)
                )
            
            console.print(table)
            console.print(f"\n[bold cyan]Total shift changes found: {len(shift_changes)}[/bold cyan]")

    except SQLAlchemyError as e:
        console.print(f"[bold red]Database error occurred:[/bold red]")
        pprint(e)
    except ImportError as e:
        console.print(f"[bold red]Import error:[/bold red] {e}")
        console.print("Please ensure all necessary modules are installed and paths are correct.")
        console.print("You might need to run 'pip install rich sqlalchemy psycopg2-binary sqlmodel'.") # Added sqlmodel
    except Exception as e:
        console.print(f"[bold red]An unexpected error occurred:[/bold red]")
        pprint(e)

if __name__ == "__main__":
    # Check if rich is installed
    try:
        import rich
    except ImportError:
        print("The 'rich' library is not installed. Please install it by running:")
        print("pip install rich")
        print("This script uses 'rich' for better terminal output.")
        sys.exit(1)
        
    asyncio.run(view_all_shift_changes()) 