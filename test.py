import os
import shutil

# Ingresa la ruta raíz donde quieres limpiar
root_path = input("Ingresa la ruta raíz: ").strip()

if not os.path.exists(root_path):
    print(f"La ruta {root_path} no existe.")
else:
    deleted_files = 0
    deleted_dirs = 0

    for dirpath, dirnames, filenames in os.walk(root_path, topdown=False):
        # Eliminar archivos .pyc
        for file in filenames:
            if file.endswith(".pyc"):
                full_path = os.path.join(dirpath, file)
                try:
                    os.remove(full_path)
                    deleted_files += 1
                    print(f"Archivo eliminado: {full_path}")
                except Exception as e:
                    print(f"No se pudo eliminar {full_path}: {e}")

        # Eliminar carpetas __pycache__
        for dirname in dirnames:
            if dirname == "__pycache__":
                full_dir_path = os.path.join(dirpath, dirname)
                try:
                    shutil.rmtree(full_dir_path)
                    deleted_dirs += 1
                    print(f"Directorio eliminado: {full_dir_path}")
                except Exception as e:
                    print(f"No se pudo eliminar {full_dir_path}: {e}")

    print(f"\nProceso finalizado.\nArchivos eliminados: {deleted_files}\nDirectorios eliminados: {deleted_dirs}")
