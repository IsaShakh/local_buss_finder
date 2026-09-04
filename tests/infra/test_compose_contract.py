import json
import subprocess
import unittest
from pathlib import Path


class ComposeContractTest(unittest.TestCase):
    """Protect the externally visible local infrastructure contract."""

    def load_config(self, *files: str) -> dict:
        command = ["docker", "compose"]
        for path in files:
            command.extend(("-f", path))
        command.extend(("config", "--format", "json"))
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(result.stdout)

    def test_stateful_services_are_declared(self) -> None:
        services = self.load_config()["services"]

        self.assertTrue({"garage", "postgres", "redis"}.issubset(services))

    def test_postgis_uses_the_project_multi_arch_image(self) -> None:
        postgres = self.load_config()["services"]["postgres"]

        self.assertEqual(
            "local-business-intelligence/postgis:17.11-3.6.4",
            postgres["image"],
        )
        self.assertEqual(
            str(Path("infrastructure/postgres").resolve()),
            postgres["build"]["context"],
        )

    def test_postgis_layer_uses_the_compatible_trixie_base(self) -> None:
        dockerfile = Path("infrastructure/postgres/Dockerfile").read_text()

        self.assertIn("postgres:17.11-trixie@sha256:", dockerfile)

    def test_backend_environment_uses_redis_as_broker_only(self) -> None:
        environment = self.load_config()["x-backend-environment"]

        self.assertEqual("redis://redis:6379/0", environment["CELERY_BROKER_URL"])
        self.assertEqual("true", environment.get("CELERY_TASK_IGNORE_RESULT"))
        self.assertNotIn("CELERY_RESULT_BACKEND", environment)

    def test_development_lock_pins_build_tool_dependencies(self) -> None:
        development_lock = Path("backend/requirements/development.txt").read_text()

        self.assertIn("pip==", development_lock)
        self.assertIn("setuptools==", development_lock)

    def test_python_redis_client_matches_celery_transport_support(self) -> None:
        base_requirements = Path("backend/requirements/base.in").read_text()

        self.assertIn("celery[redis]==5.5.3", base_requirements)
        self.assertIn("redis==5.2.1", base_requirements)

    def test_stateful_ports_are_bound_only_to_loopback(self) -> None:
        services = self.load_config()["services"]

        for service_name in ("garage", "postgres", "redis"):
            with self.subTest(service=service_name):
                published_ports = services[service_name].get("ports", [])
                self.assertTrue(published_ports)
                self.assertTrue(
                    all(port.get("host_ip") == "127.0.0.1" for port in published_ports)
                )

    def test_stateful_data_uses_named_volumes(self) -> None:
        config = self.load_config()

        self.assertEqual(
            {"garage_data", "garage_meta", "postgres_data", "redis_data"},
            set(config.get("volumes", {})),
        )

    def test_stateful_services_have_real_readiness_checks(self) -> None:
        services = self.load_config()["services"]
        expected_checks = {
            "postgres": "pg_isready",
            "redis": "redis-cli ping",
            "garage": "/garage stats -a",
        }

        for service_name, expected_check in expected_checks.items():
            with self.subTest(service=service_name):
                healthcheck = services[service_name].get("healthcheck", {})
                test_command = " ".join(healthcheck.get("test", []))
                self.assertIn(expected_check, test_command)

    def test_garage_bootstraps_a_private_s3_bucket(self) -> None:
        garage = self.load_config()["services"]["garage"]
        command = garage.get("command") or []
        command_text = command if isinstance(command, str) else " ".join(command)
        environment = garage.get("environment", {})

        self.assertIn("--single-node", command_text)
        self.assertIn("--default-bucket", command_text)
        self.assertEqual(
            "local-business-intelligence",
            environment.get("GARAGE_DEFAULT_BUCKET"),
        )
        self.assertNotEqual(
            environment.get("GARAGE_DEFAULT_ACCESS_KEY"),
            environment.get("GARAGE_DEFAULT_SECRET_KEY"),
        )
        self.assertIsNotNone(garage.get("healthcheck"))

    def test_celery_workers_become_healthy_only_with_expected_queue(self) -> None:
        services = self.load_config()["services"]

        for service_name, queue_name in (
            ("celery-discovery", "discovery"),
            ("celery-normalization", "normalization"),
        ):
            with self.subTest(service=service_name):
                self.assertIn(service_name, services)
                service = services[service_name]
                self.assertEqual(services["backend"]["image"], service["image"])
                self.assertNotIn("build", service)
                self.assertEqual("true", service["environment"]["CELERY_TASK_IGNORE_RESULT"])
                self.assertNotIn("CELERY_RESULT_BACKEND", service["environment"])
                command = service["command"]
                command_text = command if isinstance(command, str) else " ".join(command)
                self.assertIn(f"--hostname={queue_name}@%h", command_text)
                healthcheck = " ".join(service["healthcheck"]["test"])
                self.assertIn("active_queues", healthcheck)
                self.assertIn(f"== {{'{queue_name}'}}", healthcheck)

    def test_e2e_override_removes_host_ports(self) -> None:
        services = self.load_config("docker-compose.yml", "docker-compose.e2e.yml")[
            "services"
        ]

        for service_name in ("garage", "postgres", "redis"):
            with self.subTest(service=service_name):
                self.assertNotIn("ports", services[service_name])


if __name__ == "__main__":
    unittest.main()
