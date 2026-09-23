import ChatApp from "@/components/ChatApp";
import { currentAccount } from "@/lib/server/accounts";

export default async function Home() {
  // Resolved on the server, since only server code can read the login cookie
  return <ChatApp account={await currentAccount()} />;
}
