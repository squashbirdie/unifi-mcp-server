"""VPN data models."""

from pydantic import BaseModel, ConfigDict, Field


class SiteToSiteVPN(BaseModel):
    """UniFi Site-to-Site IPsec VPN configuration."""

    id: str = Field(..., description="VPN ID", alias="_id")
    name: str = Field(..., description="VPN name")
    enabled: bool = Field(True, description="Whether VPN is enabled")
    vpn_type: str = Field("ipsec-vpn", description="VPN type")
    purpose: str = Field("site-vpn", description="Network purpose")

    # IPsec peer settings
    ipsec_peer_ip: str | None = Field(None, description="Remote peer IP address")
    ipsec_local_ip: str | None = Field(None, description="Local WAN IP address")
    remote_vpn_subnets: list[str] | None = Field(None, description="Remote subnets")
    x_ipsec_pre_shared_key: str | None = Field(None, description="Pre-shared key")

    # IKE settings
    ipsec_key_exchange: str | None = Field(None, description="IKE version (ikev1/ikev2)")
    ipsec_ike_encryption: str | None = Field(None, description="IKE encryption")
    ipsec_ike_hash: str | None = Field(None, description="IKE hash algorithm")
    ipsec_ike_dh_group: int | None = Field(None, description="IKE DH group")
    ipsec_ike_lifetime: int | None = Field(None, description="IKE lifetime in seconds")

    # ESP settings
    ipsec_esp_encryption: str | None = Field(None, description="ESP encryption")
    ipsec_esp_hash: str | None = Field(None, description="ESP hash algorithm")
    ipsec_esp_dh_group: int | None = Field(None, description="ESP DH group")
    ipsec_esp_lifetime: int | None = Field(None, description="ESP lifetime in seconds")
    ipsec_pfs: bool | None = Field(None, description="Perfect Forward Secrecy")

    # Other settings
    ipsec_profile: str | None = Field(None, description="IPsec profile")
    ipsec_interface: str | None = Field(None, description="WAN interface")
    ipsec_dynamic_routing: bool | None = Field(None, description="Dynamic routing enabled")
    route_distance: int | None = Field(None, description="Route distance/metric")
    site_id: str | None = Field(None, description="Site ID")

    model_config = ConfigDict(populate_by_name=True)


class VPNTunnel(BaseModel):
    """UniFi Site-to-Site VPN Tunnel."""

    id: str = Field(..., description="VPN tunnel ID", alias="_id")
    name: str = Field(..., description="Tunnel name")
    enabled: bool | None = Field(None, description="Whether tunnel is enabled")
    peer_address: str | None = Field(None, description="Remote peer address")
    local_network: str | None = Field(None, description="Local network CIDR")
    remote_network: str | None = Field(None, description="Remote network CIDR")
    status: str | None = Field(None, description="Connection status")
    ipsec_profile: str | None = Field(None, description="IPSec profile name")
    site_id: str | None = Field(None, description="Site ID")

    model_config = ConfigDict(populate_by_name=True)


class VPNServer(BaseModel):
    """UniFi VPN Server configuration."""

    id: str = Field(..., description="VPN server ID", alias="_id")
    name: str = Field(..., description="Server name")
    enabled: bool | None = Field(None, description="Whether server is enabled")
    server_type: str | None = Field(None, description="VPN type (L2TP, PPTP, etc.)")
    network: str | None = Field(None, description="VPN client network")
    dns_servers: list[str] | None = Field(None, description="DNS servers for clients")
    max_connections: int | None = Field(None, description="Maximum concurrent connections")
    site_id: str | None = Field(None, description="Site ID")

    model_config = ConfigDict(populate_by_name=True)
