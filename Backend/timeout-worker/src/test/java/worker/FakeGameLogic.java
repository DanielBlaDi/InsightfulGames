package worker;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

/**
 * Gateway interno falso. Responde GET /internal/logic/games/expired con la lista configurada y
 * cada POST .../{id}/{timeout|expire} con la respuesta configurada para esa ruta (200 por defecto).
 */
final class FakeGateway implements AutoCloseable{

    record Request(String method, String path, String query, String contentType, String body){}

    record Reply(int status, String body){}

    final List<Request> requests = new CopyOnWriteArrayList<>();
    final Map<String, Reply> replies = new ConcurrentHashMap<>();
    volatile Reply expired = new Reply(200, "[]");

    private final HttpServer server;

    FakeGateway() throws IOException{
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/", this::handle);
        server.start();
    }

    String url(){
        return "http://127.0.0.1:" + server.getAddress().getPort();
    }

    void replyTo(String path, int status, String code){
        replies.put(path, new Reply(status, code == null ? "{}"
            : "{\"error\":{\"code\":\"" + code + "\",\"message\":\"m\"}}"));
    }

    List<Request> posts(){
        return requests.stream().filter(r -> r.method().equals("POST")).toList();
    }

    @Override
    public void close(){
        server.stop(0);
    }

    private void handle(HttpExchange ex) throws IOException{
        String path = ex.getRequestURI().getPath();
        String body = new String(ex.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);
        requests.add(new Request(ex.getRequestMethod(), path, ex.getRequestURI().getQuery(),
            ex.getRequestHeaders().getFirst("Content-Type"), body));

        Reply reply;
        if(ex.getRequestMethod().equals("GET") && path.equals("/internal/logic/games/expired")){
            reply = expired;
        }else if(ex.getRequestMethod().equals("POST")){
            reply = replies.getOrDefault(path, new Reply(200,
                "{\"gameId\":\"x\",\"status\":\"finished\",\"result\":\"black\",\"endReason\":\"timeout\",\"finishedAt\":\"2026-10-29T15:20:00Z\"}"));
        }else{
            reply = new Reply(404, "{\"error\":{\"code\":\"NOT_FOUND\",\"message\":\"Ruta inexistente\"}}");
        }
        byte[] out = reply.body().getBytes(StandardCharsets.UTF_8);
        ex.getResponseHeaders().add("Content-Type", "application/json");
        ex.sendResponseHeaders(reply.status(), out.length);
        ex.getResponseBody().write(out);
        ex.close();
    }
}
