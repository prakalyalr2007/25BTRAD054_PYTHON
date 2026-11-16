def length_converter():
    print("\nLength Converter")
    print("1. Kilometers to Meters")
    print("2. Meters to Kilometers")
    print("3. Centimeters to Meters")
    print("4. Meters to Centimeters")

    choice = int(input("Enter your choice: "))
    value = float(input("Enter the value: "))

    if choice == 1:
        print(f"{value} km = {value * 1000} m")
    elif choice == 2:
        print(f"{value} m = {value / 1000} km")
    elif choice == 3:
        print(f"{value} cm = {value / 100} m")
    elif choice == 4:
        print(f"{value} m = {value * 100} cm")
    else:
        print("Invalid choice")


def weight_converter():
    print("\nWeight Converter")
    print("1. Kilograms to Grams")
    print("2. Grams to Kilograms")
    print("3. Kilograms to Pounds")
    print("4. Pounds to Kilograms")

    choice = int(input("Enter your choice: "))
    value = float(input("Enter the value: "))

    if choice == 1:
        print(f"{value} kg = {value * 1000} g")
    elif choice == 2:
        print(f"{value} g = {value / 1000} kg")
    elif choice == 3:
        print(f"{value} kg = {value * 2.20462:.2f} lb")
    elif choice == 4:
        print(f"{value} lb = {value / 2.20462:.2f} kg")
    else:
        print("Invalid choice")


def temperature_converter():
    print("\nTemperature Converter")
    print("1. Celsius to Fahrenheit")
    print("2. Fahrenheit to Celsius")

    choice = int(input("Enter your choice: "))
    value = float(input("Enter the temperature: "))

    if choice == 1:
        fahrenheit = (value * 9/5) + 32
        print(f"{value}°C = {fahrenheit:.2f}°F")
    elif choice == 2:
        celsius = (value - 32) * 5/9
        print(f"{value}°F = {celsius:.2f}°C")
    else:
        print("Invalid choice")


while True:
    print("\n====== UNIT CONVERTER ======")
    print("1. Length Converter")
    print("2. Weight Converter")
    print("3. Temperature Converter")
    print("4. Exit")

    option = int(input("Enter your option: "))

    if option == 1:
        length_converter()
    elif option == 2:
        weight_converter()
    elif option == 3:
        temperature_converter()
    elif option == 4:
        print("Thank you for using the Unit Converter!")
        break
    else:
        print("Invalid option! Please try again.")
