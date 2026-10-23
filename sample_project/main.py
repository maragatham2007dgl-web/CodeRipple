from services import format_message
from calculations import add_numbers

def run_demo():
    total = add_numbers(4, 5)
    return format_message(total)

if __name__ == "__main__":
    print(run_demo())
