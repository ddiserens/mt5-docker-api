#!/usr/bin/env python3
"""
Improved script for MetaTrader5 initialization with Pydantic validation
Includes signal handling, caching, and integrity verification
"""
import os
import sys
import subprocess
import time
import logging
import signal
import hashlib
import json
from pathlib import Path
from typing import Optional, Dict
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from datetime import datetime, timedelta

# Add app directory to the path
sys.path.append('/app')

try:
    from config import settings
except ImportError:
    # Use default configuration if config.py does not exist
    class DefaultSettings:
        wine_prefix = os.environ.get('WINEPREFIX', '/config/.wine')
        mt5_port = int(os.environ.get('MT5_PORT', '8001'))
        log_level = os.environ.get('LOG_LEVEL', 'INFO')
        max_retries = 3
        download_timeout = 300
        cache_enabled = True
        cache_ttl_days = 7
        mono_url = "https://dl.winehq.org/wine/wine-mono/8.0.0/wine-mono-8.0.0-x86.msi"
        python_url = "https://www.python.org/ftp/python/3.9.0/python-3.9.0.exe"
        mt5_download_url = "https://download.mql5.com/cdn/web/metaquotes.ltd/mt5/mt5setup.exe"
        required_packages = ["MetaTrader5==5.0.36", "mt5linux", "pyxdg"]
        
        def get_cache_dir(self):
            return Path(self.wine_prefix).parent / ".cache"
        
        def dict(self):
            return {k: v for k, v in self.__dict__.items() if not k.startswith('_')}
    
    settings = DefaultSettings()

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper() if hasattr(settings, 'log_level') else 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Known checksums for integrity verification
KNOWN_CHECKSUMS = {
    "wine-mono-8.0.0-x86.msi": "3f7b1cd6b7842c09142082e50ece97abe848a033a0838f029c35ce973926c275",
    "python-3.9.0.exe": "fd2e4c52fb5a0f6c0d7f8c31131a21c57b0728d9e8b3ed7c207ceea8f1078918",
}

class GracefulKiller:
    """Handles signals for graceful shutdown"""
    kill_now = False
    
    def __init__(self):
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)
    
    def _handle_signal(self, signum, frame):
        logger.info(f"Signal {signum} received. Starting graceful shutdown...")
        self.kill_now = True

class MT5Installer:
    """Improved MetaTrader5 installer with cache and verification"""
    
    def __init__(self):
        self.settings = settings
        self.session = self._create_session()
        self.cache_dir = Path("/config/.cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.killer = GracefulKiller()
        self.processes = []
        
    def _create_session(self) -> requests.Session:
        """Create HTTP session with retries"""
        session = requests.Session()
        retry = Retry(
            total=self.settings.max_retries,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504]
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        return session
    
    def _calculate_checksum(self, file_path: Path) -> str:
        """Calculate SHA256 checksum of a file"""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    
    def _verify_checksum(self, file_path: Path, expected_checksum: Optional[str]) -> bool:
        """Verify file integrity"""
        if not expected_checksum:
            logger.warning(f"No known checksum for {file_path.name}")
            return True
        
        actual_checksum = self._calculate_checksum(file_path)
        if actual_checksum == expected_checksum:
            logger.info(f"Checksum verified correctly for {file_path.name}")
            return True
        else:
            logger.error(f"Incorrect checksum for {file_path.name}")
            logger.error(f"Expected: {expected_checksum}")
            logger.error(f"Actual: {actual_checksum}")
            return False
    
    def _get_cache_metadata(self, url: str) -> Dict:
        """Get cache metadata"""
        cache_metadata_file = self.cache_dir / f"{hashlib.md5(url.encode()).hexdigest()}.meta"
        if cache_metadata_file.exists():
            with open(cache_metadata_file, 'r') as f:
                return json.load(f)
        return {}
    
    def _save_cache_metadata(self, url: str, metadata: Dict):
        """Save cache metadata"""
        cache_metadata_file = self.cache_dir / f"{hashlib.md5(url.encode()).hexdigest()}.meta"
        with open(cache_metadata_file, 'w') as f:
            json.dump(metadata, f)
    
    def download_file(self, url: str, dest_path: Path, expected_checksum: Optional[str] = None) -> bool:
        """Download file with cache, progress, and validation"""
        try:
            # Check if it should terminate
            if self.killer.kill_now:
                return False
            
            # Check cache
            cache_file = self.cache_dir / dest_path.name
            cache_metadata = self._get_cache_metadata(url)
            
            # Use cache if it exists and is valid
            if cache_file.exists() and cache_metadata:
                cache_time = datetime.fromisoformat(cache_metadata.get('timestamp', ''))
                if datetime.now() - cache_time < timedelta(days=7):
                    logger.info(f"Using file from cache: {dest_path.name}")
                    cache_file.rename(dest_path)
                    return True
            
            logger.info(f"Downloading {url} to {dest_path}")
            response = self.session.get(
                url, 
                stream=True, 
                timeout=self.settings.download_timeout
            )
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(dest_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if self.killer.kill_now:
                        logger.info("Download interrupted by termination signal")
                        return False
                    
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            progress = (downloaded / total_size) * 100
                            if downloaded % (1024 * 1024) == 0:  # Log every MB
                                logger.info(f"Progress: {progress:.1f}% ({downloaded/1024/1024:.1f}MB/{total_size/1024/1024:.1f}MB)")
            
            # Verify checksum if available
            filename = dest_path.name
            expected = expected_checksum or KNOWN_CHECKSUMS.get(filename)
            if not self._verify_checksum(dest_path, expected):
                dest_path.unlink()
                return False
            
            # Save to cache
            cache_file = self.cache_dir / dest_path.name
            dest_path.link_to(cache_file)
            self._save_cache_metadata(url, {
                'timestamp': datetime.now().isoformat(),
                'checksum': self._calculate_checksum(dest_path)
            })
            
            logger.info(f"Download complete: {dest_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error downloading {url}: {e}")
            return False
    
    def run_command(self, cmd: list, check: bool = True, background: bool = False) -> Optional[subprocess.Popen]:
        """Execute command with logging and process handling"""
        try:
            if self.killer.kill_now:
                return None
            
            logger.info(f"Executing: {' '.join(cmd)}")
            
            if background:
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                self.processes.append(process)
                return process
            else:
                result = subprocess.run(
                    cmd,
                    check=check,
                    capture_output=True,
                    text=True
                )
                if result.stdout:
                    logger.debug(f"STDOUT: {result.stdout}")
                if result.stderr:
                    logger.debug(f"STDERR: {result.stderr}")
                return result
        except subprocess.CalledProcessError as e:
            logger.error(f"Error executing command: {e}")
            if check:
                raise
            return None
    
    def install_mono(self):
        """Install Wine Mono"""
        if self.killer.kill_now:
            return
        
        mono_path = Path(self.settings.wine_prefix) / "drive_c" / "windows" / "mono"
        
        if mono_path.exists():
            logger.info("Mono is already installed")
            return
        
        logger.info("Installing Wine Mono...")
        mono_installer = Path("/tmp/mono.msi")
        
        if self.download_file(self.settings.mono_url, mono_installer):
            self.run_command([
                "wine", "msiexec", "/i", 
                str(mono_installer), "/qn"
            ], check=False)
            mono_installer.unlink()
            logger.info("Mono installed successfully")
    
    def install_mt5(self):
        """Install MetaTrader5"""
        if self.killer.kill_now:
            return
        
        mt5_exe = Path(self.settings.wine_prefix) / "drive_c" / "Program Files" / "MetaTrader 5" / "terminal64.exe"
        
        if mt5_exe.exists():
            logger.info("MetaTrader5 is already installed")
            return
        
        logger.info("Installing MetaTrader5...")
        
        # Configure Wine for Windows 10
        self.run_command([
            "wine", "reg", "add", 
            "HKEY_CURRENT_USER\\Software\\Wine",
            "/v", "Version", "/t", "REG_SZ", 
            "/d", self.settings.wine_version, "/f"
        ])
        
        mt5_installer = Path("/tmp/mt5setup.exe")
        
        if self.download_file(self.settings.mt5_download_url, mt5_installer):
            # Install MT5
            process = subprocess.Popen(
                ["wine", str(mt5_installer), "/auto"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # Wait up to 5 minutes or until termination signal
            timeout = 300
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                if self.killer.kill_now:
                    process.terminate()
                    return
                
                if process.poll() is not None:
                    break
                
                time.sleep(1)
            
            if process.poll() is None:
                logger.warning("MT5 installation taking longer than expected")
                process.terminate()
            
            mt5_installer.unlink()
            
            if mt5_exe.exists():
                logger.info("MetaTrader5 installed successfully")
            else:
                logger.error("Error installing MetaTrader5")
    
    def install_python_wine(self):
        """Install Python in Wine"""
        if self.killer.kill_now:
            return
        
        try:
            result = self.run_command(["wine", "python", "--version"], check=False)
            if result and result.returncode == 0:
                logger.info(f"Python already installed in Wine: {result.stdout}")
                return
        except:
            pass
        
        logger.info("Installing Python in Wine...")
        python_installer = Path("/tmp/python-installer.exe")
        
        if self.download_file(self.settings.python_url, python_installer):
            self.run_command([
                "wine", str(python_installer),
                "/quiet", "InstallAllUsers=1", "PrependPath=1"
            ], check=False)
            python_installer.unlink()
            
            # Update pip
            self.run_command([
                "wine", "python", "-m", "pip",
                "install", "--upgrade", "pip"
            ], check=False)
    
    def install_python_packages(self):
        """Install required Python packages"""
        if self.killer.kill_now:
            return
        
        logger.info("Installing Python packages...")
        
        for package in self.settings.required_packages:
            if self.killer.kill_now:
                return
            
            # In Wine
            logger.info(f"Installing {package} in Wine...")
            self.run_command([
                "wine", "python", "-m", "pip",
                "install", "--no-cache-dir", package
            ], check=False)
            
            # In Linux
            logger.info(f"Installing {package} in Linux...")
            self.run_command([
                "pip3", "install",
                "--no-cache-dir", package
            ], check=False)
    
    def start_mt5(self):
        """Start MetaTrader5"""
        if self.killer.kill_now:
            return
        
        mt5_exe = Path(self.settings.wine_prefix) / "drive_c" / "Program Files" / "MetaTrader 5" / "terminal64.exe"
        
        if mt5_exe.exists():
            logger.info("Starting MetaTrader5...")
            self.run_command(["wine", str(mt5_exe)], background=True)
        else:
            logger.error("MetaTrader5 not found")
    
    def start_mt5_server(self):
        """Start mt5linux server"""
        if self.killer.kill_now:
            return
        
        logger.info(f"Starting mt5linux server on port {self.settings.mt5_port}...")
        
        self.run_command([
            "python3", "-m", "mt5linux",
            "--host", "0.0.0.0",
            "-p", str(self.settings.mt5_port),
            "-w", "wine", "python.exe"
        ], background=True)
        
        # Verify that the server is running
        time.sleep(5)
        result = self.run_command(["ss", "-tuln"], check=False)
        
        if result and f":{self.settings.mt5_port}" in result.stdout:
            logger.info(f"mt5linux server running on port {self.settings.mt5_port}")
        else:
            logger.error("Could not verify the mt5linux server")
    
    def cleanup(self):
        """Clean up processes on termination"""
        logger.info("Cleaning up processes...")
        for process in self.processes:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
    
    def run(self):
        """Run complete installation"""
        try:
            logger.info("=== Starting MetaTrader5 installation ===")
            logger.info(f"Configuration: {self.settings.dict()}")
            
            # Create necessary directories
            Path(self.settings.wine_prefix).mkdir(parents=True, exist_ok=True)
            
            # Installation steps
            steps = [
                self.install_mono,
                self.install_mt5,
                self.install_python_wine,
                self.install_python_packages,
                self.start_mt5,
                self.start_mt5_server
            ]
            
            for step in steps:
                if self.killer.kill_now:
                    logger.info("Installation interrupted by termination signal")
                    break
                step()
            
            if not self.killer.kill_now:
                logger.info("=== Installation completed ===")
                
                # Keep the process alive
                while not self.killer.kill_now:
                    time.sleep(1)
            
        except Exception as e:
            logger.error(f"Error during installation: {e}")
            raise
        finally:
            self.cleanup()
            logger.info("Script terminated")

if __name__ == "__main__":
    installer = MT5Installer()
    installer.run()