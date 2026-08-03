from app.integrations.network.detect import AddressCandidate, _is_dockerish, pick_auto_ip


def make_candidate(
    ip: str,
    *,
    source: str = "interface",
    interface: str | None = None,
    likely_docker: bool = False,
    is_private: bool = True,
) -> AddressCandidate:
    return AddressCandidate(
        ip=ip,
        interface=interface,
        source=source,
        likely_docker=likely_docker,
        is_private=is_private,
    )


class TestIsDockerish:
    def test_docker_interface_names(self) -> None:
        assert _is_dockerish("docker0", "192.168.1.5")
        assert _is_dockerish("br-abc123", "10.0.0.5")
        assert _is_dockerish("veth1234", "10.0.0.5")

    def test_docker_pool_ip(self) -> None:
        assert _is_dockerish("eth0", "172.18.0.2")
        assert _is_dockerish(None, "172.17.0.1")

    def test_lan_addresses_not_dockerish(self) -> None:
        # 192.168/16 is common on real LANs — must not be treated as docker.
        assert not _is_dockerish("eth0", "192.168.1.50")
        assert not _is_dockerish("wlan0", "10.20.30.40")


class TestPickAutoIp:
    def test_empty_returns_none(self) -> None:
        assert pick_auto_ip([]) is None

    def test_env_and_host_file_win(self) -> None:
        candidates = [
            make_candidate("192.168.1.10"),
            make_candidate("10.0.0.7", source="host_ip_file"),
        ]
        assert pick_auto_ip(candidates) == "10.0.0.7"

    def test_prefers_non_docker(self) -> None:
        candidates = [
            make_candidate("172.18.0.2", likely_docker=True),
            make_candidate("192.168.1.10"),
        ]
        assert pick_auto_ip(candidates) == "192.168.1.10"

    def test_falls_back_to_first_when_all_docker(self) -> None:
        candidates = [make_candidate("172.18.0.2", likely_docker=True)]
        assert pick_auto_ip(candidates) == "172.18.0.2"
