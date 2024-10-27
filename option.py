import sys


def ask_for_input():
    while True:
        user_input = input("Do you want to continue/abort/skip_current? (y/n/s): ").lower()
        if user_input == 'y':
            print("Proceeding...")
            return 0  # Don't skip
        elif user_input == 'n':
            print("Aborting the program.")
            sys.exit()  # Exit the program if 'n' is chosen
        elif user_input == 's':
            print("Skipping current...")
            return 1  # Set skip_flag to 1
        else:
            print("Invalid input, please enter 'y', 'n', or 's'.")


def ask_for_allin():
    while True:
        confirmation = input(
            "All in Means download everything at once.\n"
            "This may take a long time and require over 100G of disk space.\n"
            " Are you sure? (y/n): ").lower()
        if confirmation == 'y':
            print("All in! Ensure more than 100G disk space available in current directory!!!")
            print("May take a looooooong time to finish!!!")
            return 1  # Set allin_flag to 1
        elif confirmation == 'n':
            print("Cancelled 'All in' operation.")
            return 0
        else:
            print("Invalid input, please enter 'y' or 'n'.")