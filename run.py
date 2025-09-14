#!/usr/bin/env python3
"""
Development server runner dengan automatic ngrok setup
Run this script to start FastAPI + auto-expose dengan ngrok
"""
import os
import sys
import asyncio
import subprocess
import time
import requests
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DevelopmentServer:
    def __init__(self):
        self.fastapi_process = None
        self.ngrok_process = None
        self.ngrok_url = None
        self.fastapi_port = int(os.getenv("PORT", 8000))
        
    def check_dependencies(self):
        """Check if required dependencies are installed"""
        logger.info("🔍 Checking dependencies...")
        
        # Check Python packages
        try:
            import fastapi
            import uvicorn
            import websockets
            logger.info("✅ Python dependencies OK")
        except ImportError as e:
            logger.error(f"❌ Missing Python dependency: {e}")
            logger.info("💡 Run: pip install -r requirements.txt")
            return False
        
        # Check ngrok installation
        try:
            result = subprocess.run(["ngrok", "version"], capture_output=True, text=True)
            if result.returncode == 0:
                logger.info(f"✅ Ngrok installed: {result.stdout.strip()}")
            else:
                raise FileNotFoundError
        except FileNotFoundError:
            logger.error("❌ Ngrok not found")
            logger.info("💡 Install ngrok from: https://ngrok.com/download")
            logger.info("💡 Or use: brew install ngrok (macOS) / choco install ngrok (Windows)")
            return False
        
        return True
    
    def setup_ngrok_auth(self):
        """Setup ngrok authtoken if not configured"""
        logger.info("🔑 Checking ngrok authentication...")
        
        try:
            # Check if authtoken is configured
            result = subprocess.run(["ngrok", "config", "check"], capture_output=True, text=True)
            if "valid" in result.stdout.lower():
                logger.info("✅ Ngrok authtoken configured")
                return True
            else:
                logger.warning("⚠️  Ngrok authtoken not configured")
                logger.info("💡 Get your authtoken from: https://dashboard.ngrok.com/get-started/your-authtoken")
                logger.info("💡 Then run: ngrok config add-authtoken YOUR_AUTHTOKEN")
                
                # Ask user if they want to continue without authtoken (limited features)
                response = input("Continue without authtoken? (y/n): ").lower().strip()
                return response == 'y'
                
        except Exception as e:
            logger.warning(f"⚠️  Could not check ngrok auth: {e}")
            return True  # Continue anyway
    
    def start_fastapi(self):
        """Start FastAPI server"""
        logger.info(f"🚀 Starting FastAPI server on port {self.fastapi_port}...")
        
        try:
            self.fastapi_process = subprocess.Popen([
                sys.executable, "-m", "uvicorn",
                "main:app",
                "--host", "0.0.0.0",
                "--port", str(self.fastapi_port),
                "--reload",
                "--log-level", "info"
            ])
            
            # Wait for server to start
            time.sleep(3)
            
            # Check if server is running
            try:
                response = requests.get(f"http://localhost:{self.fastapi_port}/health", timeout=5)
                if response.status_code == 200:
                    logger.info("✅ FastAPI server started successfully")
                    return True
                else:
                    logger.error(f"❌ FastAPI server returned status {response.status_code}")
                    return False
            except requests.RequestException:
                logger.error("❌ Could not connect to FastAPI server")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error starting FastAPI: {e}")
            return False
    
    def start_ngrok(self):
        """Start ngrok tunnel"""
        logger.info("🌐 Starting ngrok tunnel...")
        
        try:
            # Start ngrok
            self.ngrok_process = subprocess.Popen([
                "ngrok", "http", str(self.fastapi_port),
                "--log", "stdout"
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            # Wait for ngrok to start
            time.sleep(3)
            
            # Get ngrok URL
            self.ngrok_url = self.get_ngrok_url()
            
            if self.ngrok_url:
                logger.info(f"✅ Ngrok tunnel started: {self.ngrok_url}")
                return True
            else:
                logger.error("❌ Could not get ngrok URL")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error starting ngrok: {e}")
            return False
    
    def get_ngrok_url(self, retries=5):
        """Get ngrok public URL from API"""
        for i in range(retries):
            try:
                response = requests.get("http://localhost:4040/api/tunnels", timeout=5)
                if response.status_code == 200:
                    tunnels = response.json().get("tunnels", [])
                    for tunnel in tunnels:
                        if tunnel.get("proto") == "https":
                            return tunnel.get("public_url")
                
                logger.info(f"⏳ Waiting for ngrok tunnel... ({i+1}/{retries})")
                time.sleep(2)
                
            except requests.RequestException:
                logger.info(f"⏳ Ngrok API not ready... ({i+1}/{retries})")
                time.sleep(2)
        
        return None
    
    def print_endpoints(self):
        """Print all available endpoints"""
        if not self.ngrok_url:
            return
        
        logger.info("\n" + "="*60)
        logger.info("🎉 QURAN TRANSCRIPT API READY!")
        logger.info("="*60)
        logger.info(f"📡 Public URL: {self.ngrok_url}")
        logger.info(f"🏠 Local URL:  http://localhost:{self.fastapi_port}")
        logger.info(f"📊 Ngrok Web Interface: http://localhost:4040")
        logger.info("")
        logger.info("📋 API Endpoints:")
        logger.info(f"   • Docs: {self.ngrok_url}/docs")
        logger.info(f"   • Health: {self.ngrok_url}/health")
        logger.info(f"   • Quran API: {self.ngrok_url}/quran/{{surah}}/{{ayah}}")
        logger.info(f"   • Start Session: {self.ngrok_url}/live/start/{{surah}}/{{ayah}}")
        logger.info(f"   • Move Ayah: {self.ngrok_url}/live/move/{{session_id}} (PATCH)")
        logger.info("")
        logger.info("🔌 WebSocket Endpoints:")
        logger.info(f"   • Live Transcript: {self.ngrok_url.replace('https://', 'wss://')}/ws/live/{{session_id}}")
        logger.info(f"   • Monitor: {self.ngrok_url.replace('https://', 'wss://')}/ws/monitor")
        logger.info("")
        logger.info("📱 Flutter WebSocket Messages:")
        logger.info('   • Move Ayah: {"type": "move_ayah", "ayah": 5, "position": 0}')
        logger.info('   • Transcript: {"type": "transcript", "text": "...", "is_final": true}')
        logger.info('   • Ping: {"type": "ping"}')
        logger.info("")
        logger.info("📱 Flutter Configuration:")
        logger.info(f'   const String baseUrl = "{self.ngrok_url}";')
        logger.info(f'   const String wsUrl = "{self.ngrok_url.replace("https://", "wss://")}";')
        logger.info("")
        logger.info("🛠️  Development Commands:")
        logger.info("   • Ctrl+C: Stop servers")
        logger.info("   • View logs: Check terminal output")
        logger.info("   • Restart: Run this script again")
        logger.info("="*60)
    
    def cleanup(self):
        """Cleanup processes"""
        logger.info("\n🧹 Cleaning up...")
        
        if self.fastapi_process:
            logger.info("🛑 Stopping FastAPI server...")
            self.fastapi_process.terminate()
            try:
                self.fastapi_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.fastapi_process.kill()
        
        if self.ngrok_process:
            logger.info("🛑 Stopping ngrok tunnel...")
            self.ngrok_process.terminate()
            try:
                self.ngrok_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.ngrok_process.kill()
        
        logger.info("✅ Cleanup completed")
    
    def run(self):
        """Main run method"""
        try:
            logger.info("🏁 Starting Quran Transcript API Development Server")
            logger.info("="*60)
            
            # Check dependencies
            if not self.check_dependencies():
                return False
            
            # Setup ngrok auth
            if not self.setup_ngrok_auth():
                logger.error("❌ Ngrok setup failed")
                return False
            
            # Start FastAPI
            if not self.start_fastapi():
                logger.error("❌ Failed to start FastAPI")
                return False
            
            # Start ngrok
            if not self.start_ngrok():
                logger.error("❌ Failed to start ngrok")
                return False
            
            # Print endpoints
            self.print_endpoints()
            
            # Keep running
            logger.info("\n⏳ Server running... Press Ctrl+C to stop")
            try:
                while True:
                    time.sleep(1)
                    
                    # Check if processes are still alive
                    if self.fastapi_process and self.fastapi_process.poll() is not None:
                        logger.error("❌ FastAPI process died")
                        break
                    
                    if self.ngrok_process and self.ngrok_process.poll() is not None:
                        logger.error("❌ Ngrok process died")
                        break
                        
            except KeyboardInterrupt:
                logger.info("\n👋 Shutdown requested by user")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Unexpected error: {e}")
            return False
        finally:
            self.cleanup()

def main():
    """Main entry point"""
    # Check if we're in the right directory
    if not os.path.exists("main.py"):
        logger.error("❌ main.py not found. Are you in the correct directory?")
        logger.info("💡 Make sure you're in the project root directory")
        sys.exit(1)
    
    # Check if .env file exists
    if not os.path.exists(".env"):
        logger.warning("⚠️  .env file not found")
        logger.info("💡 Create .env file with your Supabase configuration")
        
        response = input("Continue anyway? (y/n): ").lower().strip()
        if response != 'y':
            sys.exit(1)
    
    # Run server
    server = DevelopmentServer()
    success = server.run()
    
    if success:
        logger.info("✅ Server shutdown successfully")
        sys.exit(0)
    else:
        logger.error("❌ Server failed to start properly")
        sys.exit(1)

if __name__ == "__main__":
    main()