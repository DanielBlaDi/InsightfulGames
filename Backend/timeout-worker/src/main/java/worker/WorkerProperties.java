package worker;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Configuración del worker (contrato, 18.5), tomada de GATEWAY_INTERNAL_URL,
 * TIMEOUT_POLL_INTERVAL_SECONDS y TIMEOUT_BATCH_LIMIT. Un valor inválido impide arrancar.
 */
@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(String gatewayInternalUrl, Integer pollIntervalSeconds, Integer batchLimit){

    public WorkerProperties{
        if(gatewayInternalUrl == null || !gatewayInternalUrl.matches("^https?://.+")){
            throw new IllegalArgumentException("GATEWAY_INTERNAL_URL debe ser una URL http(s) absoluta: " + gatewayInternalUrl);
        }
        if(pollIntervalSeconds == null || pollIntervalSeconds < 1){
            throw new IllegalArgumentException("TIMEOUT_POLL_INTERVAL_SECONDS debe ser un entero mayor que 0");
        }
        if(batchLimit == null || batchLimit < 1){
            throw new IllegalArgumentException("TIMEOUT_BATCH_LIMIT debe ser un entero mayor que 0");
        }
        gatewayInternalUrl = gatewayInternalUrl.replaceAll("/+$", "");
    }

    /**
     * Tiempo máximo sin actividad del ciclo antes de declararse no saludable:
     * diez intervalos, con un mínimo de 60 s.
     */
    public Duration staleAfter(){
        return Duration.ofSeconds(Math.max(60, 10L * pollIntervalSeconds));
    }
}
