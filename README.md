# docker
These are my docker compose scripts, intended for use in Portainer Stacks. Below are notes on my self-hosted lab and its applications and services. 

Some of these items were set up before I learned how Portainer uses stacks, and were either added individually or with templates. I will be converting them to compose stacks where possible.

The host
-------
Hardware: Decommed Datto Siris NAS-style unit  
OS: Proxmox VE  
LXC:
- DNS (AdGuard), separated and not Docker so I don't break the Internet for the family
  
VMs and their Docker containers:
- applications-vm
  - Flame homepage - Starting point for my day with applications and frequently used bookmarks
  - IT Tools - A wide variety of techy tools!
  - Ntfy - Notification service, hoping to replace Push Bullet
  - Nginx Proxy Manager (npm) - Ingress management
  - Portainer - Manage docker stacks, containers, volumes across both VMs
  - Picoshare - Share files and text securely
  - Remotely - Remote access to systems I help maintain
  - Rustdesk - Remote access, largely replaced by Remotely for easier use and sharing of acces
  - Uptime Kuma - Monitor and alert for when my services go offline, and the ham radio repeaters and packet radio nodes I help support go offline
  - Watchtower - Keeps containers up to date
  - Wireguard VPN - wg-easy
- games-vm
  - EmulatorJS - Host emulators and ROMs for play over web browser
  - Minecraft - Bedrock Edition survival server for family use
  - portainer_agent - Connects to Portainer on applications-vm for one-stop management of Docker
  - Veloren - Open souce MMORPG, hosted locally for family/friend use
  - Watchtower - Keeps containers up to date

The network 
-----------
The real domain name is obfuscated to protect the innocent.

DNS: 
- Namecheap domain, e.g.: mydomain.com
- A cron job on the applications-vm polls a hosted cpanel URL to update subdomain dns.mydomain.com to update the IP of my home
- All other subdomains are CNAME to the dns.mydomain.com

Ingress: 
- Nginx Proxy Manager routes requests for specific subdomains to the appropriate docker container and port
- Forces HTTPS connections
- Access Control List prohibits access to infrastructure to LAN subnets only
