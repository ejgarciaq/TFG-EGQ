from werkzeug.security import generate_password_hash, check_password_hash


def mostrar_menu():
    print("\n=== Generador y verificador de hashes ===")
    print("1. Generar hash a partir de una contraseña")
    print("2. Verificar si una contraseña coincide con un hash")
    print("3. Salir")


def generar_hash():
    clave = input("Ingresa la contraseña: ").strip()
    if not clave:
        print("La contraseña no puede estar vacía.")
        return
    hash_nuevo = generate_password_hash(clave, method='pbkdf2:sha256', salt_length=16)
    print("\nHash generado:")
    print(hash_nuevo)


def verificar_hash():
    hash_guardado = input("Ingresa el hash: ").strip()
    if not hash_guardado:
        print("El hash no puede estar vacío.")
        return
    clave = input("Ingresa la contraseña para comprobar: ").strip()
    if not clave:
        print("La contraseña no puede estar vacía.")
        return

    try:
        valido = check_password_hash(hash_guardado, clave)
    except ValueError as exc:
        print("\nError:", exc)
        print("El valor ingresado no tiene el formato de hash válido para Werkzeug.")
        return

    print("\nResultado:")
    if valido:
        print("Sí coincide")
        print("Contraseña recuperada:", clave)
    else:
        print("No coincide")


if __name__ == "__main__":
    while True:
        mostrar_menu()
        opcion = input("Elige una opción: ").strip()
        if opcion == "1":
            generar_hash()
        elif opcion == "2":
            verificar_hash()
        elif opcion == "3":
            print("Saliendo...")
            break
        else:
            print("Opción inválida.")

