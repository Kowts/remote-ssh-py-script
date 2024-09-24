import os
import time
import asyncssh
import asyncio
import logging
from typing import Tuple, Optional

# Configure the logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Connect to a remote SSH server using password-based authentication.
async def connect_ssh(hostname: str, port: int, username: str, password: str, keepalive_interval: int = 30) -> asyncssh.SSHClient:
    """
    Args:
        hostname (str): The hostname or IP address of the server.
        port (int): The SSH port.
        username (str): The SSH username.
        password (str): The SSH password.
        keepalive_interval (int): The interval in seconds to send keepalive messages. Defaults to 30 seconds.

    Returns:
        asyncssh.SSHClient: An SSH client object.

    Raises:
        ValueError: If an SSH-related error occurs.
    """

    logger.info(f"Connecting to SSH server at {hostname}:{port}")

    try:
        # Connect to the SSH server with keepalive_interval
        ssh_client = await asyncssh.connect(
            hostname,
            port=port,
            username=username,
            password=password,
            known_hosts=None,
            keepalive_interval=keepalive_interval
        )
        logger.info("Successfully connected to the SSH server.")
        return ssh_client
    except asyncssh.Error as e:
        logger.error(f"SSH connection error: {e}")
        raise ValueError(f"SSH connection error: {e}") from e


async def disconnect_ssh(ssh_client: asyncssh.SSHClient) -> None:
    """
    Closes an active SSH client connection.

    This function ensures that the SSH connection is properly closed and all associated resources are released. It is important to call this function after all SSH operations are completed to avoid resource leaks.

    Args:
        ssh_client (asyncssh.SSHClient): An active SSH client connection to be closed.

    Usage:
        ssh_client = await connect_ssh(hostname, port, username, password)
        # Perform operations using the SSH connection
        await disconnect_ssh(ssh_client)
    """
    if ssh_client is not None:
        ssh_client.close()
        await ssh_client.wait_closed()
        logger.info("SSH connection closed successfully.")


# Upload a local file to a remote server using SFTP.
async def upload_file(ssh_client: asyncssh.SSHClientConnection, local_file_path: str, remote_folder: str, new_filename: str) -> bool:
    """
    Uploads a file to a remote server over SFTP.

    Args:
        ssh_client (asyncssh.SSHClientConnection): An active SSH client connection.
        local_file_path (str): The path to the local file to upload.
        remote_folder (str): The path to the remote folder where the file should be placed.
        new_filename (str): The desired name of the file on the remote server.

    Raises:
        FileNotFoundError: If the local file does not exist.
        ValueError: If an SFTP-related error occurs during file upload.
    """
    try:
        async with ssh_client.start_sftp_client() as sftp_client:
            remote_path = f"{remote_folder}/{new_filename}"
            await sftp_client.put(local_file_path, remote_path)
            return True  # File uploaded successfully
    except FileNotFoundError:
        logger.error(f"Local file not found: {local_file_path}")
        return False  # Local file not found
    except asyncssh.SFTPError as sftp_error:
        logger.error(f"SFTP error during file upload: {sftp_error}")
        return False  # SFTP error occurred


# Download a file from a remote server using SFTP.
async def download_file(ssh_client: asyncssh.SSHClientConnection, remote_file_path: str, local_folder: str, new_filename: str) -> bool:
    """
    Downloads a file from a remote server over SFTP.

    Args:
        ssh_client (asyncssh.SSHClientConnection): An active SSH client connection.
        remote_file_path (str): The path to the remote file to download.
        local_folder (str): The path to the local folder where the file should be saved.
        new_filename (str): The desired name of the file on the local machine.

    Raises:
        FileNotFoundError: If the remote file does not exist.
        ValueError: If an SFTP-related error occurs during file download.
    """
    try:
        async with ssh_client.start_sftp_client() as sftp_client:
            local_path = os.path.join(local_folder, new_filename)
            await sftp_client.get(remote_file_path, local_path)
            return os.path.exists(local_path)  # File downloaded successfully

    except FileNotFoundError as e:
        raise FileNotFoundError(f"Remote file not found: {remote_file_path}") from e
    except asyncssh.SFTPError as sftp_error:
        raise ValueError(f"SFTP error during file download: {sftp_error}") from sftp_error


# Execute a command on the remote server and return the output.
async def execute_command(ssh_client: asyncssh.SSHClient, command: str, wait_for_response: bool = True, check_interval: int = 10, timeout: Optional[int] = None) -> Tuple[str, int, float]:
    """
    Executes a command on a remote server using an SSH client asynchronously.

    Args:
        ssh_client (asyncssh.SSHClient): An instance of an SSHClient connected to the remote server.
        command (str): The command to be executed on the remote server.
        wait_for_response (bool, optional): Flag indicating whether to wait for the command's execution to complete and to capture its output. Defaults to True.
        check_interval (int, optional): The interval in seconds to check for the command's completion. Defaults to 10 seconds.
        timeout (int, optional): The maximum time in seconds to wait for the command to complete. Defaults to None (no timeout).
    Returns:
        Tuple[str, int, float]: A tuple containing the output of the executed command, the exit status, and the execution time in seconds if `wait_for_response` is True, otherwise an empty string, exit status, and execution time of 0.0.

    Raises:
        ValueError: If there's an SSH error during command execution, encapsulating the original `asyncssh.Error`.
    """

    logger.info(f"Executing command: {command}")

    try:
        async with ssh_client.create_process(command) as process:
            if wait_for_response:
                start_time = time.time()
                if timeout is not None:
                    await asyncio.wait_for(process.wait_closed(), timeout)
                else:
                    await process.wait_closed()  # Wait for the process to finish

                end_time = time.time()
                stdout = await process.stdout.read()
                stderr = await process.stderr.read()
                exit_status = process.exit_status

                logger.info(f"Command executed successfully: {command}")
                logger.info(f"stdout: {stdout}")
                logger.error(f"stderr: {stderr}")

                execution_time = round(end_time - start_time)
                logger.info(f"Execution time: {execution_time} seconds")

                return (stdout.decode('utf-8', errors='replace') if isinstance(stdout, bytes) else stdout, exit_status, execution_time)
            else:
                logger.info("Command sent without waiting for response.")
                while not process.exit_status_ready():
                    await asyncio.sleep(check_interval)
                return ("", process.exit_status, 0.0)

    except asyncssh.Error as ssh_error:
        logger.error(f"SSH error during command execution: {ssh_error}")
        raise ValueError(f"SSH error during command execution: {ssh_error}") from ssh_error
    except asyncio.TimeoutError as e:
        logger.error(f"Command execution timed out after {timeout} seconds.")
        raise asyncio.TimeoutError(f"Command execution timed out after {timeout} seconds.") from e


# Check if a file exists in a remote folder.
async def check_remote_file(ssh_client: asyncssh.SSHClientConnection, remote_file_path: str) -> bool:
    """
    Args:
        ssh_client (asyncssh.SSHClient): An SSH client object.
        remote_file_path (str): The path to the remote file to check.

    Returns:
        bool: True if the file exists, False otherwise.
    """
    try:
        async with ssh_client.start_sftp_client() as sftp_client:
            return bool(await sftp_client.exists(remote_file_path))
    except asyncssh.SFTPError:
        return False


# Find the first file in a remote directory that starts with a given prefix.
async def find_file(ssh_client: asyncssh.SSHClientConnection, remote_directory: str, prefix: str) -> Optional[str]:
    """
    Searches for the first file in the specified remote directory that starts with the given prefix.

    Args:
        ssh_client (asyncssh.SSHClientConnection): An active SSH client connection.
        remote_directory (str): The path of the remote directory to search in.
        prefix (str): The prefix to match for file names

    Returns:
        str: The name of the first file that starts with the prefix, or None if no such file is found.
    """
    try:
        async with ssh_client.start_sftp_client() as sftp_client:
            file_list = await sftp_client.listdir(remote_directory)
            for filename in file_list:
                if filename.startswith(prefix):
                    return filename
        return None
    except asyncssh.SFTPError:
        return None
