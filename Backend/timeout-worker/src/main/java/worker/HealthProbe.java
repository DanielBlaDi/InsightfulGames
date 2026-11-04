package worker;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

/**
 * Opción -health del ejecutable (contrato, 18.3): consulta el /health del proceso en marcha y
 * termina con 0 solo si responde 200 con status ok. No arranca Spring.
 */
final class HealthProbe{

    static final String FLAG = "-health";

    private HealthProbe(){}

    static boolean requested(String[] args){
        for(String arg : args){
            if(FLAG.equals(arg)){
                return true;
            }
        }
        return false;
    }

    /** Código de salida: 0 saludable, 1 en cualquier otro caso. */
    static int run(String port){
        if(port == null || !port.matches("\\d{1,5}")){
            System.err.println("health: PORT no está definido o no es un número");
            return 1;
        }
        try{
            HttpClient client = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(2)).build();
            HttpRequest request = HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + "/health"))
                .timeout(Duration.ofSeconds(3))
                .GET()
                .build();
            HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());
            boolean ok = response.statusCode() == 200 && response.body().replace(" ", "").contains("\"status\":\"ok\"");
            if(!ok){
                System.err.println("health: " + response.statusCode() + " " + response.body());
            }
            return ok ? 0 : 1;
        }catch(Exception e){
            System.err.println("health: " + e);
            return 1;
        }
    }
}
