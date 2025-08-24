from werkzeug.security import generate_password_hash

clave = "Tartaro1981."
hash_nuevo = generate_password_hash(clave, method='pbkdf2:sha256', salt_length=16)

print("Hash generado:", hash_nuevo)

